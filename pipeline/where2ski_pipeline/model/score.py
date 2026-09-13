"""Factor normalisation, blockers, weighted scores and badges (docs/CONCEPT.md §6)."""

from __future__ import annotations

from .. import config
from .snow import DayWeather, SnowAssessment

AVALANCHE_FACTOR = {1: 1.0, 2: 0.8, 3: 0.35, 4: 0.0, 5: 0.0}


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _ramp(x: float, x0: float, x1: float) -> float:
    """1 at x<=x0, 0 at x>=x1, linear in between."""
    if x1 == x0:
        return 1.0 if x <= x0 else 0.0
    return clamp((x1 - x) / (x1 - x0))


def fresh_snow_factor(snow: SnowAssessment) -> float:
    return clamp(0.6 * min(1.0, snow.hn24 / 25.0) + 0.4 * min(1.0, snow.hn72 / 50.0))


def sun_vis_factor(w: DayWeather) -> float:
    sun = min(1.0, w.sun_hours / 7.0)
    fog = 1.0 - (w.low_cloud_pct or 0.0) / 100.0
    f = 0.6 * sun + 0.4 * fog
    if w.precip_mm > 10:
        f *= 0.6
    if w.visibility_m is not None and w.visibility_m < 1000:
        f *= 0.7
    return clamp(f)


def wind_factor(w: DayWeather) -> float:
    g = w.gust_max_top
    if g is None:
        return 0.8
    if g <= 30:
        return 1.0
    if g <= 60:
        return 1.0 - 0.6 * (g - 30) / 30.0
    if g <= 80:
        return 0.4 - 0.4 * (g - 60) / 20.0
    return 0.0


def temperature_factor(w: DayWeather) -> float:
    t = w.t_mean_day_mid
    if t is None:
        return 0.7
    if -12 <= t <= 2:
        return 1.0
    if t < -12:
        return _ramp(-t, 12, 22)
    return _ramp(t, 2, 8)


def base_factor(snow: SnowAssessment) -> float:
    if snow.hs is None:
        return 0.6
    return clamp(snow.hs / 80.0)


def travel_factor(travel_min: int | None) -> float:
    if travel_min is None:
        return 0.7
    return clamp(1.0 - 0.6 * (travel_min - 60) / 90.0) if travel_min > 60 else 1.0


def avalanche_factor(level: int | None) -> float:
    if level is None:
        return 0.7
    return AVALANCHE_FACTOR.get(level, 0.0)


def build_factors(snow: SnowAssessment, weather: DayWeather, level: int | None, travel_min: int | None,
                  crowd: float) -> dict:
    return {
        "fresh_snow": round(fresh_snow_factor(snow), 3),
        "snow_quality_freeride": round(snow.value_freeride, 3),
        "snow_quality_piste": round(snow.value_piste, 3),
        "avalanche": round(avalanche_factor(level), 3),
        "sun_vis": round(sun_vis_factor(weather), 3),
        "wind": round(wind_factor(weather), 3),
        "temperature": round(temperature_factor(weather), 3),
        "base": round(base_factor(snow), 3),
        "travel": round(travel_factor(travel_min), 3),
        "crowd": round(crowd, 3),
    }


def blockers(mode: str, snow: SnowAssessment, weather: DayWeather, level: int | None, is_open: bool) -> list[str]:
    out = []
    if not is_open:
        out.append("resort closed (outside season)")
    if snow.hs is not None:
        if mode == "piste" and snow.hs < config.BASE_MIN_PISTE:
            out.append(f"base too thin ({snow.hs:.0f} cm)")
        if mode == "freeride" and snow.hs < config.BASE_MIN_FREERIDE:
            out.append(f"base too thin for off-piste ({snow.hs:.0f} cm)")
    if mode == "freeride" and level is not None and level >= 4:
        out.append(f"avalanche danger level {level}")
    if weather.precip_mm > 8 and snow.hn24 < 3 and (weather.t_mean_day_mid or 0) > 1:
        out.append("rain most of the day")
    return out


def score(mode: str, factors: dict, weights: dict | None = None) -> float:
    w = dict(weights or config.WEIGHTS[mode])
    total = 0.0
    wsum = 0.0
    for key, weight in w.items():
        if weight <= 0:
            continue
        fkey = f"snow_quality_{mode}" if key == "snow_quality" else key
        val = factors.get(fkey)
        if val is None:
            continue
        total += weight * float(val)
        wsum += weight
    return round(100.0 * total / wsum, 1) if wsum else 0.0


def badges(snow: SnowAssessment, weather: DayWeather) -> list[str]:
    out = []
    if snow.hn48 >= 20 and weather.sun_hours >= 4 and (weather.t_mean_day_mid or 99) <= 0:
        out.append("powder_day")
    if weather.sun_hours >= 6 and (weather.gust_max_top or 0) < 40:
        out.append("bluebird")
    if (weather.low_cloud_base_pct or 0) >= 70 and weather.sun_hours >= 4 and \
            weather.t_mean_day_top is not None and weather.t_mean_day_base is not None and \
            weather.t_mean_day_top >= weather.t_mean_day_base - 1:
        out.append("inversion")
    if snow.state == "corn":
        out.append("corn_morning")
    if weather.snowfall_cm >= 15:
        out.append("storm_skiing")
    return out


def confidence(lead: int, has_station: bool, has_bulletin: bool) -> float:
    c = config.LEAD_CONFIDENCE[min(lead, len(config.LEAD_CONFIDENCE) - 1)]
    if not has_station:
        c *= 0.8
    if not has_bulletin:
        c *= 0.9
    return round(c, 2)
