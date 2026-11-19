"""Snow surface as an hourly history (docs/PLAN.md WP4).

One pass per elevation band and aspect walks from the first hour of the
series to the last and carries the state of the surface: what lies on top,
what lies beneath, how wet it is, how often it has melted and refrozen, and
whether wind has stripped or loaded it. Unlike the rule list in snow.py it
knows the order of events: snow on a crust is not a crust on snow.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from .. import config
from .precip import wet_bulb
from .solar import ASPECT_AZIMUTH, hourly_radiation, slope_irradiance

_H = timedelta(hours=1)
FIRM_UNDER = {"crust": "crust", "rain_crust": "ice", "corn_frozen": "crust"}  # everything else counts as firm


@dataclass
class HourState:
    time: datetime
    kind: str = "hard"          # powder, wind_packed, moist, wet, crust, rain_crust, corn_frozen, corn_soft, hard
    new_cm: float = 0.0         # settled depth of snow lying on the last firm surface
    under: str = "firm"         # firm, crust or ice
    wet: float = 0.0            # liquid water index of the surface, 0..1
    cycles: int = 0             # melt-refreeze cycles since the last snowfall of 10 cm or more
    loaded: bool = False        # wind has added snow to this aspect
    rained: bool = False
    hours_since_snow: float = 1e9
    q: float = 0.0              # surface energy balance, W/m²
    cold: float = 0.0           # cold content, Wh/m²: energy needed to warm the surface to 0 °C before it melts
    deposited_cm: float = 0.0   # snow fallen since the last firm surface, before settling
    melting: bool = False       # energy left after repaying the cold content: the surface is at 0 °C


def _angle(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return 360.0 - d if d > 180.0 else d


def measured_increments(history, times: list[datetime]) -> list[float | None]:
    """New snow per hour from a station's snow height: the rise above the highest of the three hours before,
    1 cm or more. None where the station has no reading."""
    if history is None:
        return [None] * len(times)
    hs = {t: (h or {}).get("hs") for t, h in history.hourly.items()}
    out = []
    for t in times:
        now = hs.get(t)
        before = [hs.get(t - _H * k) for k in (1, 2, 3)]
        before = [b for b in before if b is not None]
        if now is None or not before:
            out.append(None)
            continue
        inc = now - max(before)
        out.append(min(inc, config.SURFACE_MAX_MEASURED_CM_H) if inc >= 1.0 else 0.0)
    return out


def simulate(band, top, aspect: str, lat: float, lon: float, history=None, now: datetime | None = None,
             radiation=None, increments=None) -> list[HourState]:
    """Walk every hour of ``band``. ``top`` gives gusts and wind direction; ``history`` (a station near this band)
    gives measured air temperature and new snow for hours before ``now`` (local, naive)."""
    c = config
    rad = radiation if radiation is not None else hourly_radiation(band, lat, lon)
    temps, rh = band.get("temperature_2m"), band.get("relative_humidity_2m")
    snow, rain, cloud = band.get("snowfall"), band.get("rain"), band.get("cloud_cover")
    gusts, wdir = top.get("wind_gusts_10m"), top.get("wind_direction_10m")
    inc = increments if increments is not None else [None] * len(band.times)
    st = HourState(time=band.times[0] if band.times else datetime.min)
    event_cm = 0.0
    neg_hours = 0
    out: list[HourState] = []
    for i, t in enumerate(band.times):
        past = now is not None and t < now
        ta = temps[i]
        if past and history is not None:
            measured = (history.hourly.get(t) or {}).get("ta")
            ta = measured if measured is not None else ta
        if ta is None:
            out.append(replace(st, time=t))
            continue
        tw = wet_bulb(ta, rh[i])
        s = snow[i] or 0.0
        if past and inc[i] is not None and tw <= c.TW_SNOW_MEASURED:
            s = max(s, inc[i])
        r = rain[i] or 0.0

        # 1. snowfall
        if s >= 0.1:
            if st.new_cm < 1.0:
                st.under = FIRM_UNDER.get(st.kind, "firm")
                event_cm = 0.0
                st.deposited_cm = 0.0
            st.new_cm += s
            st.deposited_cm += s
            event_cm += s
            st.hours_since_snow = 0.0
            if event_cm >= 10.0:
                st.cycles = 0
            if tw > 0.0:
                if st.new_cm >= 1.0:
                    st.kind = "moist"
            elif st.new_cm >= c.SURFACE_POWDER_MIN_CM or (st.under in ("crust", "ice") and st.new_cm >= 1.0):
                st.kind, st.wet, st.rained, st.loaded = "powder", 0.0, False, False
        else:
            st.hours_since_snow += 1.0

        # 2. rain
        if r >= 0.2:
            st.kind, st.rained = "wet", True
            st.wet = max(st.wet, 0.6)

        # energy at the surface of this aspect
        elev, az, dni, dhi = rad[i]
        sw = slope_irradiance(elev, az, dni, dhi, aspect)
        albedo = c.ALBEDO_OLD + (c.ALBEDO_NEW - c.ALBEDO_OLD) * math.exp(-st.hours_since_snow / c.ALBEDO_DECAY_H)
        if st.kind in ("moist", "wet", "corn_soft"):
            albedo = min(albedo, c.ALBEDO_OLD)
        longwave = c.LW_CLEAR - (c.LW_CLEAR - c.LW_CLOUDY) * (cloud[i] or 0.0) / 100.0
        st.q = (1.0 - albedo) * sw + c.SENSIBLE_W_PER_C * ta - longwave

        # 3. melt, 4. refreeze; a cold surface first has to warm to 0 °C
        melt_q = 0.0
        if st.q > 0.0:
            used = min(st.cold, st.q)
            st.cold -= used
            melt_q = st.q - used
        else:
            st.cold = min(c.COLD_CONTENT_MAX_WH, st.cold - st.q)
        st.melting = melt_q > 0.0
        if melt_q > 0.0:
            neg_hours = 0
            st.wet = min(1.0, st.wet + melt_q / c.MELT_W_PER_WET)
            k = st.kind
            if k in ("powder", "wind_packed") and st.wet > 0.15:
                st.kind = "wet" if st.wet > 0.5 else "moist"
            elif k == "corn_frozen" and st.wet >= 0.1:
                st.kind = "corn_soft"
            elif k in ("crust", "rain_crust", "hard") and st.wet >= 0.1:
                st.kind = "corn_soft" if st.cycles >= c.CORN_CYCLES else "moist"
            if st.kind in ("moist", "corn_soft") and st.wet > 0.5:
                st.kind = "wet"
        elif st.q <= 0.0:
            neg_hours += 1
            if st.wet > 0.0 and neg_hours >= 2:
                if st.wet >= 0.1:
                    st.cycles += 1
                st.kind = "rain_crust" if st.rained else ("corn_frozen" if st.cycles >= c.CORN_CYCLES else "crust")
                st.under = FIRM_UNDER[st.kind]
                st.new_cm, st.wet, st.loaded, st.deposited_cm = 0.0, 0.0, False, 0.0

        # 5. wind
        g, d = gusts[i], wdir[i]
        if aspect is not None and g is not None and d is not None and g >= c.WIND_PACK_GUST \
                and st.kind == "powder" and ta < 0.0:
            diff = _angle(ASPECT_AZIMUTH[aspect], d)  # wind direction is where the wind comes from
            if diff <= 45.0:
                st.new_cm *= 0.5
                st.kind = "wind_packed"
            elif diff >= 135.0 and not st.loaded:
                st.new_cm *= 1.3
                st.loaded = True

        # 6. settling
        tau = c.SETTLE_TAU_COLD_H if ta <= -5.0 else (
            c.SETTLE_TAU_WARM_H if ta >= 0.0 else
            c.SETTLE_TAU_WARM_H + (c.SETTLE_TAU_COLD_H - c.SETTLE_TAU_WARM_H) * (-ta / 5.0))
        floor = c.SETTLE_FLOOR * st.deposited_cm
        if st.new_cm > floor:
            st.new_cm = floor + (st.new_cm - floor) * math.exp(-1.0 / tau)
        if st.kind == "powder" and st.new_cm < 1.0:
            st.kind = {"crust": "crust", "ice": "rain_crust"}.get(st.under, "hard")
        out.append(replace(st, time=t))
    return out


def value(st: HourState, mode: str) -> float:
    """Skiing value 0..1 of a surface (docs/PLAN.md 8.2)."""
    fr = mode == "freeride"
    k = st.kind
    if k == "powder":
        if st.under in ("crust", "ice") and st.new_cm < 12.0:
            return 0.25 if fr else 0.8
        if st.new_cm < 5.0:
            return 0.3 + 0.2 * st.new_cm / 5.0 if fr else 0.8
        return 0.5 + 0.5 * min(1.0, (st.new_cm - 5.0) / 20.0) if fr else 0.9
    table = {
        "wind_packed": (0.5, 0.85), "moist": (0.45, 0.6), "corn_soft": (0.75, 0.7), "corn_frozen": (0.3, 0.6),
        "crust": (0.15, 0.6), "wet": (0.2, 0.4), "rain_crust": (0.05, 0.4), "hard": (0.3, 0.7),
    }
    f, p = table.get(k, (0.3, 0.7))
    return f if fr else p


def label(st: HourState) -> str:
    """Public state name, shared with the rule model where the meaning is the same."""
    k = st.kind
    if k == "powder":
        if st.under in ("crust", "ice") and st.new_cm < 12.0:
            return "dust_on_crust"
        return "fresh_powder" if st.hours_since_snow <= 36 else "settled_powder"
    return {"wind_packed": "wind_affected", "wet": "rain_soaked" if st.rained else "wet", "corn_soft": "corn",
            "hard": "hardpack"}.get(k, k)


ASPECTS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def simulate_resort(mid, top, lat: float, lon: float, history=None, now: datetime | None = None) -> dict:
    """{band: {aspect: [HourState, ...]}} for the mid and top band; the station history belongs to the mid band."""
    out = {}
    for band, series, hist in (("mid", mid, history), ("top", top, None)):
        rad = hourly_radiation(series, lat, lon)
        inc = measured_increments(hist, series.times)
        out[band] = {a: simulate(series, top, a, lat, lon, history=hist, now=now, radiation=rad, increments=inc)
                     for a in ASPECTS}
    out["_index"] = {t: i for i, t in enumerate(mid.times)}
    return out


def assess(sims: dict, day, rose: dict, flagged: set, weights: dict) -> dict | None:
    """Best of the configured hours of ``day``: values per aspect (bands weighted by their share of the runs),
    aggregated with the aspect rose like the rule model (70 % weighted mean, 30 % best sector)."""
    idx = sims["_index"]
    best = None
    for hour in config.SURFACE_HOURS:
        t = datetime.combine(day, datetime.min.time()) + timedelta(hours=hour)
        i = idx.get(t)
        if i is None:
            continue
        per = {}
        for a in ASPECTS:
            m, tp = sims["mid"][a][i], sims["top"][a][i]
            vf = weights["mid"] * value(m, "freeride") + weights["top"] * value(tp, "freeride")
            vp = weights["mid"] * value(m, "piste") + weights["top"] * value(tp, "piste")
            per[a] = (min(vf, 0.2) if a in flagged else vf, vp, m, tp)
        relevant = [a for a in ASPECTS if rose[a] >= 0.15] or [max(ASPECTS, key=lambda a: rose[a])]
        best_a = max(relevant, key=lambda a: (per[a][0], rose[a]))
        agg_f = min(1.0, 0.7 * sum(rose[a] * per[a][0] for a in ASPECTS) + 0.3 * per[best_a][0])
        agg_p = sum(rose[a] * per[a][1] for a in ASPECTS)
        if best is None or agg_f > best["value_freeride"]:
            best = {"hour": hour, "value_freeride": agg_f, "per": per, "best_aspect": best_a}
        if best is not None:
            best["value_piste"] = max(best.get("value_piste", 0.0), agg_p)
    if best is None:
        return None
    per = best["per"]
    dominant = max(ASPECTS, key=lambda a: rose[a])
    rep = per[dominant][2]
    return {
        "state": label(rep),
        "value_freeride": round(best["value_freeride"], 3),
        "value_piste": round(best["value_piste"], 3),
        "best_hour": best["hour"],
        "best_aspect": best["best_aspect"],
        "aspect": dominant,
        "new_on_top_cm": round(sum(rose[a] * per[a][2].new_cm for a in ASPECTS), 1),
        "under": rep.under,
        "loaded_aspects": [a for a in ASPECTS if per[a][3].loaded or per[a][2].loaded],
        "by_aspect": {a: {"share": round(rose[a], 3), "state": label(per[a][2]), "state_top": label(per[a][3]),
                          "value_freeride": round(per[a][0], 2), "value_piste": round(per[a][1], 2),
                          "capped": a in flagged, "new_cm": round(per[a][2].new_cm, 1)} for a in ASPECTS},
    }


def melt_check(mid, lat: float, lon: float, history, now: datetime) -> dict | None:
    """Acceptance check of the energy balance (docs/PLAN.md 8.4): for flat ground at a station that measures the
    snow-surface temperature, does "melting" agree with a measured surface at -0.5 °C or warmer, over past
    daytime hours with snow on the ground?"""
    if history is None:
        return None
    rad = hourly_radiation(mid, lat, lon)
    states = simulate(mid, mid, None, lat, lon, history=history, now=now, radiation=rad)
    hours = agree = false_melt = missed_melt = 0
    for st, (elev, _, _, _) in zip(states, rad):
        h = history.hourly.get(st.time) or {}
        tss, hs = h.get("tss"), h.get("hs")
        if st.time >= now or elev <= 5.0 or tss is None or hs is None or hs < 10.0:
            continue
        hours += 1
        measured = tss >= -0.5
        agree += st.melting == measured
        false_melt += st.melting and not measured
        missed_melt += measured and not st.melting
    return {"station": history.station, "hours": hours, "agree": agree, "false_melt": false_melt,
            "missed_melt": missed_melt} if hours else None
