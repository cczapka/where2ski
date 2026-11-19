"""Sun position and short-wave radiation on a slope (docs/PLAN.md 8.1).

Accurate to a fraction of a degree (NOAA simplified equations), which is far
better than the radiation input it is applied to.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .. import config

LOCAL = ZoneInfo(config.TIMEZONE)
ASPECT_AZIMUTH = {"N": 0.0, "NE": 45.0, "E": 90.0, "SE": 135.0, "S": 180.0, "SW": 225.0, "W": 270.0, "NW": 315.0}


def sun_position(when_utc: datetime, lat: float, lon: float) -> tuple[float, float]:
    """(elevation, azimuth) in degrees; azimuth clockwise from north."""
    doy = when_utc.timetuple().tm_yday
    hour = when_utc.hour + when_utc.minute / 60.0
    g = 2.0 * math.pi / 365.0 * (doy - 1 + (hour - 12) / 24.0)
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g) - 0.014615 * math.cos(2 * g)
                       - 0.040849 * math.sin(2 * g))
    true_solar_min = hour * 60.0 + eqtime + 4.0 * lon
    ha = math.radians(true_solar_min / 4.0 - 180.0)
    phi = math.radians(lat)
    cos_zen = math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.cos(ha)
    cos_zen = max(-1.0, min(1.0, cos_zen))
    zen = math.acos(cos_zen)
    elev = 90.0 - math.degrees(zen)
    az = math.degrees(math.atan2(math.sin(ha), math.cos(ha) * math.sin(phi) - math.tan(decl) * math.cos(phi))) + 180.0
    return elev, az % 360.0


def local_to_utc(t_local_naive: datetime) -> datetime:
    return t_local_naive.replace(tzinfo=LOCAL).astimezone(timezone.utc)


def slope_irradiance(elev: float, az: float, dni: float, dhi: float, aspect: str | None,
                     slope_deg: float = 25.0) -> float:
    """W/m² on a slope of the given aspect: projected direct beam plus sky-view diffuse.
    aspect None means flat ground."""
    if elev <= 0.0:
        return 0.0
    e = math.radians(elev)
    if aspect is None:
        return max(0.0, dni * math.sin(e)) + dhi
    s = math.radians(slope_deg)
    cos_inc = math.cos(s) * math.sin(e) + math.sin(s) * math.cos(e) * math.cos(math.radians(az - ASPECT_AZIMUTH[aspect]))
    return max(0.0, dni * cos_inc) + dhi * (1.0 + math.cos(s)) / 2.0


def clear_sky(elev: float) -> tuple[float, float]:
    """Rough clear-sky (DNI, diffuse) for when the weather service gives no radiation."""
    if elev <= 0.0:
        return 0.0, 0.0
    m = 1.0 / max(math.sin(math.radians(elev)), 0.05)
    return 1000.0 * 0.75 ** m, 60.0 * math.sin(math.radians(elev)) + 20.0


def hourly_radiation(series, lat: float, lon: float) -> list[tuple[float, float, float, float]]:
    """Per hour (sun elevation, azimuth, DNI, diffuse). Radiation values of the weather service are means over
    the preceding hour, so the sun is taken at the middle of that hour. Without radiation data, clear-sky values
    are scaled by the sunshine duration."""
    dni_s, dhi_s, sun_s = series.get("direct_normal_irradiance"), series.get("diffuse_radiation"), \
        series.get("sunshine_duration")
    out = []
    for i, t in enumerate(series.times):
        elev, az = sun_position(local_to_utc(t - timedelta(minutes=30)), lat, lon)
        dni, dhi = dni_s[i], dhi_s[i]
        if dni is None or dhi is None:
            cdni, cdhi = clear_sky(elev)
            frac = min(1.0, (sun_s[i] or 0.0) / 3600.0)
            dni, dhi = cdni * frac, cdhi * (0.6 + 0.4 * (1 - frac)) if elev > 0 else 0.0
        out.append((elev, az, float(dni), float(dhi)))
    return out
