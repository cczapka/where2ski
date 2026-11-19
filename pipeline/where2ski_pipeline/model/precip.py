"""Snowfall derived from precipitation, per elevation band (docs/PLAN.md 7.3).

The weather service's own ``snowfall`` follows the grid cell, not the
requested elevation, and converts water to snow at a fixed 0.7 cm per mm.
Here the phase comes from the wet-bulb temperature at the band and the
density of new snow from Hedstrom and Pomeroy (1998), so a band 1000 m
above the village gets snow where the village gets rain, and cold snow is
lighter than wet snow.
"""

from __future__ import annotations

import math

from .. import config

TW_ALL_SNOW = 0.0    # °C wet-bulb: all precipitation falls as snow at or below this
TW_ALL_RAIN = 1.5    # °C wet-bulb: all rain at or above this
TW_SNOW_LINE = 1.0   # °C wet-bulb: the elevation where it is reached is the snow line
RHO_WET = 200.0      # kg/m³: density of new snow at the rain limit
LAPSE = 0.0065       # °C per m, to extrapolate the snow line beyond the bands


def wet_bulb(t: float, rh: float | None) -> float:
    """Stull (2011) approximation from air temperature (°C) and relative humidity (%)."""
    if rh is None:
        return t
    rh = min(max(rh, 5.0), 99.0)
    return (t * math.atan(0.151977 * math.sqrt(rh + 8.313659)) + math.atan(t + rh) - math.atan(rh - 1.676331)
            + 0.00391838 * rh ** 1.5 * math.atan(0.023101 * rh) - 4.686035)


def snow_share(tw: float) -> float:
    if tw <= TW_ALL_SNOW:
        return 1.0
    if tw >= TW_ALL_RAIN:
        return 0.0
    return 1.0 - (tw - TW_ALL_SNOW) / (TW_ALL_RAIN - TW_ALL_SNOW)


def density(t: float, tw: float) -> float:
    """kg/m³: Hedstrom-Pomeroy below 0 °C, rising linearly to RHO_WET at the rain limit."""
    rho = 67.9 + 51.3 * math.exp(min(t, 0.0) / 2.6)
    if tw > TW_ALL_SNOW:
        rho += (RHO_WET - rho) * min(1.0, (tw - TW_ALL_SNOW) / (TW_ALL_RAIN - TW_ALL_SNOW))
    return rho


def snow_cm(precip_mm: float | None, t: float | None, rh: float | None) -> tuple[float | None, float | None]:
    """(snow cm, rain mm) of one hour."""
    if precip_mm is None or t is None:
        return None, None
    if precip_mm <= 0.0:
        return 0.0, 0.0
    tw = wet_bulb(t, rh)
    f = snow_share(tw)
    return precip_mm * f * 100.0 / density(t, tw), precip_mm * (1.0 - f)


def derive(series) -> None:
    """Add snow_derived / rain_derived and keep the service's value as snow_api. With
    config.SNOWFALL_SOURCE == "derived" the derived values replace snowfall and rain."""
    v = series.values
    pr, ta, rh = series.get("precipitation"), series.get("temperature_2m"), series.get("relative_humidity_2m")
    pairs = [snow_cm(p, t, h) for p, t, h in zip(pr, ta, rh)]
    v["snow_api"] = list(series.get("snowfall"))
    v["rain_api"] = list(series.get("rain"))
    v["snow_derived"] = [a for a, _ in pairs]
    v["rain_derived"] = [b for _, b in pairs]
    if config.SNOWFALL_SOURCE == "derived":
        v["snowfall"] = [d if d is not None else a for d, a in zip(v["snow_derived"], v["snow_api"])]
        v["rain"] = [d if d is not None else a for d, a in zip(v["rain_derived"], v["rain_api"])]


def snow_line(bands: dict) -> list[float | None]:
    """Hourly elevation (m) where the wet-bulb temperature reaches TW_SNOW_LINE, interpolated between
    the bands and extrapolated with a standard lapse rate. Stored on every band as ``snow_line_m``."""
    order = [b for b in ("base", "mid", "top") if b in bands and bands[b].elevation is not None]
    if not order:
        return []
    n = len(bands[order[0]].times)
    out: list[float | None] = []
    for i in range(n):
        pts = []
        for b in order:
            s = bands[b]
            t, h = s.get("temperature_2m")[i], s.get("relative_humidity_2m")[i]
            if t is not None:
                pts.append((float(s.elevation), wet_bulb(t, h)))
        if not pts:
            out.append(None)
            continue
        pts.sort()
        line = None
        for (z0, w0), (z1, w1) in zip(pts, pts[1:]):
            if (w0 - TW_SNOW_LINE) * (w1 - TW_SNOW_LINE) <= 0 and w0 != w1:
                line = z0 + (z1 - z0) * (w0 - TW_SNOW_LINE) / (w0 - w1)
                break
        if line is None:
            z, w = pts[0] if pts[0][1] < TW_SNOW_LINE else pts[-1]
            line = z + (w - TW_SNOW_LINE) / LAPSE
        out.append(round(max(0.0, line)))
    for b in order:
        bands[b].values["snow_line_m"] = out
    return out
