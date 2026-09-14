"""Snow supply and surface-state heuristics (docs/CONCEPT.md §4, phase-1 version).

Everything works on hourly Open-Meteo series for the mid and top elevation
bands plus optional station observations. Aspect handling is a uniform
factor until aspect roses exist in the registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from ..sources.openmeteo import HourlySeries

SNOWFALL_EVENT_CM = 5.0  # a day with at least this much counts as "last snowfall"


def _sum(vals) -> float:
    return float(sum(v for v in vals if v is not None))


def _mean(vals) -> float | None:
    xs = [v for v in vals if v is not None]
    return sum(xs) / len(xs) if xs else None


def _max(vals) -> float | None:
    xs = [v for v in vals if v is not None]
    return max(xs) if xs else None


def _min(vals) -> float | None:
    xs = [v for v in vals if v is not None]
    return min(xs) if xs else None


def snowfall_cm(series: HourlySeries, start: datetime, end: datetime) -> float:
    return _sum(series.slice("snowfall", start, end))


def last_snowfall_end(series: HourlySeries, before: datetime, lookback_days: int = 10) -> datetime | None:
    """End of the most recent 24 h window with >= SNOWFALL_EVENT_CM, scanning back hour by hour."""
    t = before
    limit = before - timedelta(days=lookback_days)
    while t > limit:
        if snowfall_cm(series, t - timedelta(hours=24), t) >= SNOWFALL_EVENT_CM:
            return t
        t -= timedelta(hours=6)
    return None


def season_factor(day: date) -> float:
    """Rough sun strength: 0.5 in December, 1.0 in March/April, 0.8 in November."""
    table = {11: 0.6, 12: 0.5, 1: 0.55, 2: 0.75, 3: 1.0, 4: 1.1, 5: 1.2}
    return table.get(day.month, 1.0)


ASPECTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
ASPECT_SUN_BASE = {"N": 0.15, "NE": 0.3, "E": 0.6, "SE": 0.85, "S": 1.0, "SW": 0.85, "W": 0.6, "NW": 0.3}
SPRING_BLEND = {10: 0.2, 11: 0.1, 12: 0.0, 1: 0.0, 2: 0.25, 3: 0.5, 4: 0.7, 5: 0.8}
UNIFORM_ROSE = {a: 1.0 / len(ASPECTS) for a in ASPECTS}
DEFAULT_ASPECT_FACTOR = 0.6


def aspect_sun_factor(aspect: str, day: date) -> float:
    """How much of the daily sunshine reaches a slope of this aspect (mid-winter: north faces almost none)."""
    base = ASPECT_SUN_BASE[aspect]
    blend = SPRING_BLEND.get(day.month, 0.5)
    return base + (1.0 - base) * blend


def normalise_rose(rose: dict | None) -> dict:
    if not rose:
        return dict(UNIFORM_ROSE)
    total = sum(float(rose.get(a, 0.0)) for a in ASPECTS)
    if total <= 0:
        return dict(UNIFORM_ROSE)
    return {a: float(rose.get(a, 0.0)) / total for a in ASPECTS}


def _hour_rows(mid: HourlySeries, history, start: datetime, end: datetime):
    """(model air T, station air T, station snow-surface T) per forecast hour in [start, end)."""
    temps = mid.get("temperature_2m")
    for i in mid.indices(start, end):
        t = mid.times[i]
        h = history.hourly.get(t) if history is not None else None
        yield temps[i], (h or {}).get("ta"), (h or {}).get("tss")


def melt_hours_between(mid: HourlySeries, history, start: datetime, end: datetime) -> int:
    """Hours with melting: surface temperature >= -0.5 °C where measured, else air temperature > 0 °C."""
    n = 0
    for model, ta, tss in _hour_rows(mid, history, start, end):
        if tss is not None:
            n += tss >= -0.5
        elif ta is not None:
            n += ta > 0.0
        elif model is not None:
            n += model > 0.0
    return n


def surface_temps(mid: HourlySeries, history, start: datetime, end: datetime) -> list[float]:
    """Best available temperature for refreeze detection: surface, else station air, else model air."""
    out = []
    for model, ta, tss in _hour_rows(mid, history, start, end):
        v = tss if tss is not None else (ta if ta is not None else model)
        if v is not None:
            out.append(v)
    return out


@dataclass
class SnowAssessment:
    state: str
    value_freeride: float
    value_piste: float
    hn24: float
    hn48: float
    hn72: float
    hs: float | None
    hs_source: str
    days_since_snow: float | None
    melt_hours: int
    sun_load: float
    cycles: int
    refreeze: bool
    rain_hours: int
    gust_max: float | None
    reasons: list[str] = field(default_factory=list)
    aspect: str | None = None
    best_aspect: str | None = None
    by_aspect: dict | None = None

    def public(self) -> dict:
        return {
            "state": self.state,
            "aspect": self.aspect,
            "best_aspect": self.best_aspect,
            "by_aspect": self.by_aspect,
            "value_freeride": round(self.value_freeride, 2),
            "value_piste": round(self.value_piste, 2),
            "hn24": round(self.hn24, 1),
            "hn48": round(self.hn48, 1),
            "hn72": round(self.hn72, 1),
            "hs": None if self.hs is None else round(self.hs),
            "hs_source": self.hs_source,
            "days_since_snow": None if self.days_since_snow is None else round(self.days_since_snow, 1),
            "melt_hours": self.melt_hours,
            "sun_load": round(self.sun_load, 1),
            "cycles": self.cycles,
            "refreeze": self.refreeze,
            "rain_hours": self.rain_hours,
            "gust_max": None if self.gust_max is None else round(self.gust_max),
            "reasons": self.reasons,
        }


def assess_day(mid: HourlySeries, top: HourlySeries, day: date, today: date,
               station_hs: float | None = None, station_hn: dict | None = None,
               aspect_factor: float = DEFAULT_ASPECT_FACTOR, glacier: bool = False,
               history=None) -> SnowAssessment:
    noon = datetime.combine(day, datetime.min.time()) + timedelta(hours=12)
    day_start = datetime.combine(day, datetime.min.time())
    day_end = day_start + timedelta(days=1)
    reasons: list[str] = []

    hn24 = snowfall_cm(mid, noon - timedelta(hours=24), noon)
    hn48 = snowfall_cm(mid, noon - timedelta(hours=48), noon)
    hn72 = snowfall_cm(mid, noon - timedelta(hours=72), noon)
    if station_hn and day == today:
        for key, val in station_hn.items():
            if val is not None:
                if key == "hn24":
                    hn24 = float(val)
                elif key == "hn48":
                    hn48 = float(val)
                elif key == "hn72":
                    hn72 = float(val)
        reasons.append("new snow from nearby station")

    # snow depth: station today (or carried forward with forecast snowfall), else model snow_depth
    hs_source = "none"
    hs = None
    if station_hs is not None:
        hs_source = "station"
        hs = float(station_hs)
        if day > today:
            future = snowfall_cm(mid, datetime.combine(today, datetime.min.time()) + timedelta(hours=12), noon)
            hs = hs + 0.7 * future  # settling
            hs_source = "station+forecast"
    else:
        depth_m = _mean(mid.slice("snow_depth", day_start, day_end))
        if depth_m is not None:
            hs = round(depth_m * 100.0, 1)
            hs_source = "model"
    if glacier and (hs is None or hs < 100):
        hs = max(hs or 0.0, 100.0)
        hs_source = "glacier"

    last_end = last_snowfall_end(mid, noon)
    since = last_end if last_end is not None else noon - timedelta(days=10)
    days_since = (noon - last_end).total_seconds() / 86400 if last_end else None

    melt_hours = melt_hours_between(mid, history, since, noon)
    rain = mid.slice("rain", since, noon)
    rain_hours = sum(1 for r in rain if r is not None and r > 0.2)
    sun_since = _sum(mid.slice("sunshine_duration", since, noon)) / 3600.0
    sun_load = sun_since * aspect_factor * season_factor(day)
    gust_max = _max(top.slice("wind_gusts_10m", since - timedelta(hours=24), noon))

    # melt/refreeze cycles: for each day between last snowfall and this day
    cycles = 0
    d = since.date()
    while d < day:
        ds = datetime.combine(d, datetime.min.time())
        tmax = _max(surface_temps(mid, history, ds + timedelta(hours=9), ds + timedelta(hours=17)))
        tmin = _min(surface_temps(mid, history, ds + timedelta(hours=20), ds + timedelta(hours=32)))
        if tmax is not None and tmin is not None and tmax > -0.5 and tmin < -1.0:
            cycles += 1
        d += timedelta(days=1)

    night_min = _min(surface_temps(mid, history, day_start - timedelta(hours=4), day_start + timedelta(hours=8)))
    refreeze = night_min is not None and night_min < -1.0
    t_day = _mean(mid.slice("temperature_2m", day_start + timedelta(hours=9), day_start + timedelta(hours=16)))
    sun_day = _sum(mid.slice("sunshine_duration", day_start, day_end)) / 3600.0
    gust_ok = gust_max is None or gust_max < 35.0

    if rain_hours > 1 and hn24 < 5:
        state, vf, vp = "rain_soaked", 0.0, 0.3
        reasons.append(f"rain on snow ({rain_hours} h since last snowfall)")
    elif t_day is not None and t_day > 3.0 and not refreeze:
        state, vf, vp = "wet", 0.2, 0.4
        reasons.append(f"warm day ({t_day:.0f} °C) without overnight refreeze")
    elif (hn72 >= 15 or hn24 >= 10) and melt_hours <= 2 and gust_ok:
        state, vf, vp = "fresh_powder", 1.0, 0.9
        reasons.append(f"{hn72:.0f} cm in 72 h, cold, calm")
    elif (hn72 >= 15 or hn24 >= 10) and melt_hours <= 2:
        state, vf, vp = "wind_affected", 0.6, 0.8
        reasons.append(f"{hn72:.0f} cm in 72 h but gusts up to {gust_max:.0f} km/h")
    elif cycles >= 3 and refreeze and sun_day >= 4:
        state, vf, vp = "corn", 0.7, 0.7
        reasons.append(f"{cycles} melt-freeze cycles, refrozen night, sunny: corn window late morning")
    elif days_since is not None and days_since <= 7 and melt_hours <= 2 and sun_load < 6:
        state, vf, vp = "settled_powder", 0.75, 0.8
        reasons.append(f"last snowfall {days_since:.0f} d ago, stayed cold and shaded")
    elif (melt_hours > 2 or sun_load >= 6) and refreeze:
        state, vf, vp = "crust", 0.15, 0.5
        reasons.append(f"melted ({melt_hours} h above 0 °C, sun load {sun_load:.0f}) then refrozen")
    else:
        state, vf, vp = "hardpack", 0.3, 0.7
        reasons.append("old snow, no recent snowfall")

    return SnowAssessment(state=state, value_freeride=vf, value_piste=vp, hn24=hn24, hn48=hn48, hn72=hn72,
                          hs=hs, hs_source=hs_source, days_since_snow=days_since, melt_hours=melt_hours,
                          sun_load=sun_load, cycles=cycles, refreeze=refreeze, rain_hours=rain_hours,
                          gust_max=gust_max, reasons=reasons)


def assess_resort_day(mid: HourlySeries, top: HourlySeries, day: date, today: date, rose: dict | None,
                      station_hs: float | None = None, station_hn: dict | None = None, glacier: bool = False,
                      history=None, flagged_aspects: set[str] | None = None) -> SnowAssessment:
    """Assess every aspect sector, then aggregate with the resort's aspect rose.

    Freeride quality is 70 % rose-weighted mean plus 30 % of the best sector
    that holds at least 15 % of the terrain (you go where the snow is good).
    Sectors flagged by an avalanche problem are capped at 0.2 for freeride.
    Piste quality is the plain rose-weighted mean.
    """
    rose_n = normalise_rose(rose)
    flagged = set(flagged_aspects or ())
    per = {a: assess_day(mid, top, day, today, station_hs=station_hs, station_hn=station_hn,
                         aspect_factor=aspect_sun_factor(a, day), glacier=glacier, history=history)
           for a in ASPECTS}
    vf = {a: (min(per[a].value_freeride, 0.2) if a in flagged else per[a].value_freeride) for a in ASPECTS}
    weighted_f = sum(rose_n[a] * vf[a] for a in ASPECTS)
    weighted_p = sum(rose_n[a] * per[a].value_piste for a in ASPECTS)
    relevant = [a for a in ASPECTS if rose_n[a] >= 0.15] or [max(ASPECTS, key=lambda a: rose_n[a])]
    best = max(relevant, key=lambda a: (vf[a], rose_n[a]))
    agg_f = min(1.0, 0.7 * weighted_f + 0.3 * vf[best])
    dominant = max(ASPECTS, key=lambda a: rose_n[a])

    rep = per[dominant]
    rep.aspect = dominant
    rep.best_aspect = best
    rep.value_freeride = round(agg_f, 3)
    rep.value_piste = round(weighted_p, 3)
    rep.by_aspect = {
        a: {
            "share": round(rose_n[a], 3),
            "state": per[a].state,
            "value_freeride": round(vf[a], 2),
            "value_piste": round(per[a].value_piste, 2),
            "capped": a in flagged,
            "sun_load": round(per[a].sun_load, 1),
        }
        for a in ASPECTS
    }
    reasons = list(rep.reasons)
    if per[best].state != rep.state:
        reasons.append(f"best aspect {best} ({int(rose_n[best] * 100)} % of terrain): {per[best].state}")
    else:
        reasons.append(f"best aspect {best} ({int(rose_n[best] * 100)} % of terrain)")
    if flagged:
        reasons.append("avalanche problem on " + "/".join(a for a in ASPECTS if a in flagged) + ": those aspects capped")
    if history is not None:
        reasons.append(f"melt/refreeze from station {history.station} measurements")
    rep.reasons = reasons
    return rep


@dataclass
class DayWeather:
    sun_hours: float
    t_min_mid: float | None
    t_max_mid: float | None
    t_mean_day_mid: float | None
    t_mean_day_top: float | None
    t_mean_day_base: float | None
    gust_max_top: float | None
    precip_mm: float
    snowfall_cm: float
    low_cloud_pct: float | None
    low_cloud_base_pct: float | None
    freezing_level_m: float | None
    visibility_m: float | None

    def public(self) -> dict:
        r = lambda v, n=1: None if v is None else round(v, n)  # noqa: E731
        return {
            "sun_hours": round(self.sun_hours, 1),
            "t_min_mid": r(self.t_min_mid),
            "t_max_mid": r(self.t_max_mid),
            "t_mean_day_mid": r(self.t_mean_day_mid),
            "t_mean_day_top": r(self.t_mean_day_top),
            "t_mean_day_base": r(self.t_mean_day_base),
            "gust_max_top": r(self.gust_max_top, 0),
            "precip_mm": round(self.precip_mm, 1),
            "snowfall_cm": round(self.snowfall_cm, 1),
            "low_cloud_pct": r(self.low_cloud_pct, 0),
            "low_cloud_base_pct": r(self.low_cloud_base_pct, 0),
            "freezing_level_m": r(self.freezing_level_m, 0),
            "visibility_m": r(self.visibility_m, 0),
        }


def day_weather(base: HourlySeries, mid: HourlySeries, top: HourlySeries, day: date) -> DayWeather:
    ds = datetime.combine(day, datetime.min.time())
    de = ds + timedelta(days=1)
    core_s, core_e = ds + timedelta(hours=9), ds + timedelta(hours=16)
    return DayWeather(
        sun_hours=_sum(mid.slice("sunshine_duration", ds + timedelta(hours=8), ds + timedelta(hours=17))) / 3600.0,
        t_min_mid=_min(mid.slice("temperature_2m", ds, de)),
        t_max_mid=_max(mid.slice("temperature_2m", ds, de)),
        t_mean_day_mid=_mean(mid.slice("temperature_2m", core_s, core_e)),
        t_mean_day_top=_mean(top.slice("temperature_2m", core_s, core_e)),
        t_mean_day_base=_mean(base.slice("temperature_2m", core_s, core_e)),
        gust_max_top=_max(top.slice("wind_gusts_10m", ds + timedelta(hours=8), ds + timedelta(hours=17))),
        precip_mm=_sum(mid.slice("precipitation", ds, de)),
        snowfall_cm=_sum(mid.slice("snowfall", ds, de)),
        low_cloud_pct=_mean(mid.slice("cloud_cover_low", core_s, core_e)),
        low_cloud_base_pct=_mean(base.slice("cloud_cover_low", core_s, core_e)),
        freezing_level_m=_mean(mid.slice("freezing_level_height", core_s, core_e)),
        visibility_m=_mean(mid.slice("visibility", core_s, core_e)),
    )
