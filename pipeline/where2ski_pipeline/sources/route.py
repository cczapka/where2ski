"""Road conditions on the drive from Munich.

Snowfall on the approach matters as much as snow at the resort: fresh snow on
the Fernpass or Gerlospass adds an hour and chain risk. Rather than calling a
routing service, the pipeline keeps a small table of the real Alpine road
waypoints used from Munich (with their true road elevations) and keeps the
ones lying close to the straight line Munich -> resort (perpendicular distance
below CORRIDOR_KM, at most MAX_WAYPOINTS of them, nearest to the line first).

The vertical position is what decides rain vs snow, so using the real road
elevation (not the terrain under a straight line) is what makes this useful.
The corridor is an approximation of the drive, not a routed path: it names the
pass you are most likely to cross, not a turn-by-turn route.
All waypoints are fetched in one batched Open-Meteo request per run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .. import config
from ..geo import haversine_km
from ..http import Http
from .openmeteo import HourlySeries, parse_hourly

log = logging.getLogger(__name__)

# name, lat, lon, road elevation in m
WAYPOINTS: list[tuple[str, float, float, float]] = [
    ("Inntal / Kufstein", 47.583, 12.166, 500),
    ("Achenpass", 47.596, 11.641, 941),
    ("Sylvensteinsee", 47.576, 11.481, 780),
    ("Garmisch / Griesen", 47.480, 10.950, 750),
    ("Fernpass", 47.363, 10.833, 1216),
    ("Zirler Berg", 47.283, 11.235, 1020),
    ("Seefelder Sattel", 47.329, 11.188, 1180),
    ("Brennerpass", 47.003, 11.506, 1370),
    ("Gerlospass", 47.231, 12.083, 1531),
    ("Pass Thurn", 47.290, 12.400, 1274),
    ("Felbertauern Nordportal", 47.132, 12.500, 1650),
    ("Grießenpass", 47.480, 12.560, 964),
    ("Arlberg", 47.130, 10.216, 1300),
    ("Reschenpass", 46.837, 10.505, 1504),
    ("Radstädter Tauernpass", 47.283, 13.545, 1738),
    ("Tauerntunnel Nord", 47.190, 13.400, 1200),
    ("Allgäu / Kempten", 47.600, 10.350, 800),
]

CORRIDOR_KM = 22.0  # how far a waypoint may lie from the straight line to count as "on the way"
MAX_WAYPOINTS = 3
MORNING = (5, 11)  # hours of the drive that matter
ROUTE_VARS = ["snowfall", "rain", "temperature_2m", "freezing_level_height"]


@dataclass
class RoadPoint:
    name: str
    elevation: float
    series: HourlySeries


def _segment_distance_km(lat: float, lon: float, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance from a point to the segment (1)-(2), equirectangular at these latitudes."""
    import math

    k = math.cos(math.radians((lat1 + lat2) / 2))
    ax, ay = (lon - lon1) * k, lat - lat1
    bx, by = (lon2 - lon1) * k, lat2 - lat1
    bb = bx * bx + by * by
    t = 0.0 if bb == 0 else max(0.0, min(1.0, (ax * bx + ay * by) / bb))
    px, py = lon1 + (lon2 - lon1) * t, lat1 + (lat2 - lat1) * t
    return haversine_km(lat, lon, py, px)


def waypoints_for(resort) -> list[tuple[str, float, float, float]]:
    """Road waypoints within the corridor of the drive, nearest to the line first.

    ``links.road_waypoints`` in the registry pins the list by name (an empty
    list means "no pass on this drive") when the corridor picks up a pass that
    is near the line but not actually driven.
    """
    links = resort.links if isinstance(resort.links, dict) else {}
    pinned = links.get("road_waypoints")
    if pinned is not None:
        wanted = {str(n) for n in pinned}
        return [w for w in WAYPOINTS if w[0] in wanted]
    home = config.HOME
    scored = []
    for name, lat, lon, ele in WAYPOINTS:
        d = _segment_distance_km(lat, lon, home["lat"], home["lon"], resort.lat, resort.lon)
        if d <= CORRIDOR_KM:
            scored.append((d, (name, lat, lon, ele)))
    scored.sort(key=lambda x: x[0])
    return [wp for _, wp in scored[:MAX_WAYPOINTS]]


def fetch_road_points(http: Http, resorts) -> dict[str, RoadPoint]:
    """One batched request for every waypoint that any resort needs."""
    needed: dict[str, tuple[str, float, float, float]] = {}
    for r in resorts:
        for wp in waypoints_for(r):
            needed[wp[0]] = wp
    if not needed:
        return {}
    items = list(needed.values())
    params = {
        "latitude": ",".join(f"{w[1]:.4f}" for w in items),
        "longitude": ",".join(f"{w[2]:.4f}" for w in items),
        "elevation": ",".join(f"{w[3]:.0f}" for w in items),
        "hourly": ",".join(ROUTE_VARS),
        "forecast_days": config.FORECAST_DAYS,
        "timezone": config.TIMEZONE,
        "models": "best_match",
    }
    data = http.get_json(config.OPEN_METEO_URL, key="openmeteo_roads.json", params=params)
    blocks = data if isinstance(data, list) else [data]
    if len(blocks) != len(items):
        log.warning("road forecast returned %d blocks for %d waypoints", len(blocks), len(items))
        return {}
    return {w[0]: RoadPoint(name=w[0], elevation=w[3], series=parse_hourly(b)) for w, b in zip(items, blocks)}


def road_report(points: list[RoadPoint], day: date) -> dict | None:
    """Worst waypoint on the morning drive: fresh snow, and rain where it is too warm."""
    start = datetime.combine(day, datetime.min.time()) + timedelta(hours=MORNING[0])
    end = datetime.combine(day, datetime.min.time()) + timedelta(hours=MORNING[1])
    worst = None
    for p in points:
        snow = sum(v for v in p.series.slice("snowfall", start, end) if v is not None)
        rain = sum(v for v in p.series.slice("rain", start, end) if v is not None)
        temps = [v for v in p.series.slice("temperature_2m", start, end) if v is not None]
        entry = {
            "waypoint": p.name,
            "elevation": round(p.elevation),
            "snowfall_cm": round(snow, 1),
            "rain_mm": round(rain, 1),
            "t_min": round(min(temps), 1) if temps else None,
        }
        # worst = most snow; on a tie the higher pass, which is the one that turns first
        if worst is None or (snow, p.elevation) > (worst["snowfall_cm"], worst["elevation"]):
            worst = entry
    if worst is None:
        return None
    worst["points"] = len(points)
    return worst


def road_factor(report: dict | None, expected: bool = True) -> float:
    """1.0 = clear roads, 0.2 = heavy snowfall on the pass during the drive.

    ``expected`` is False when the drive crosses no pass at all (motorway only),
    which is a clear road rather than missing information.
    """
    if report is None:
        return 0.9 if expected else 1.0
    snow = report.get("snowfall_cm") or 0.0
    if snow <= 0.5:
        return 1.0
    if snow >= 15.0:
        return 0.2
    return round(1.0 - 0.8 * (snow - 0.5) / 14.5, 3)
