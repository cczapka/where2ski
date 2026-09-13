"""Weather station observations from the EAWS aggregation used by lawinen.report."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .. import config
from ..geo import haversine_km
from ..http import Http

log = logging.getLogger(__name__)

# Candidate property names (lower-case, last path segment) per quantity.
KEYS = {
    "name": {"name", "stationname", "station_name", "station", "lwd_name", "title", "label"},
    "elevation": {"elevation", "ele", "alt", "altitude", "hoehe", "height", "elev", "lwd_hoehe"},
    "hs": {"hs", "snowheight", "snow_height", "sh", "snowdepth", "snow_depth", "schneehoehe"},
    "hn24": {"hn24", "hsd24", "hs24", "newsnow24", "ns24", "hn_24", "snow24", "hs_24", "hsdiff24"},
    "hn48": {"hn48", "hsd48", "hs48", "newsnow48", "ns48", "hn_48", "snow48", "hs_48", "hsdiff48"},
    "hn72": {"hn72", "hsd72", "hs72", "newsnow72", "ns72", "hn_72", "snow72", "hs_72", "hsdiff72"},
    "t_air": {"lt", "ta", "t", "temperature", "airtemperature", "air_temperature", "temp", "lufttemperatur", "tl"},
    "t_surface": {"oft", "tss", "snowsurfacetemperature", "snow_surface_temperature", "surface_temperature", "schneeoberflaechentemperatur"},
    "gust": {"wg", "gust", "windgust", "wind_gust", "boe", "ff_boe", "wsp_max", "ffx"},
    "wind": {"ws", "ff", "windspeed", "wind_speed", "wind"},
    "time": {"date", "time", "timestamp", "datetime", "datum", "obs_time", "measured_at"},
    "operator": {"operator", "provider", "source", "region", "lwd", "operator_name"},
}


@dataclass
class Station:
    name: str
    lat: float
    lon: float
    elevation: float | None
    hs: float | None = None
    hn24: float | None = None
    hn48: float | None = None
    hn72: float | None = None
    t_air: float | None = None
    t_surface: float | None = None
    gust: float | None = None
    wind: float | None = None
    time: str | None = None
    operator: str | None = None

    def public(self) -> dict:
        return {
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "elevation": self.elevation,
            "hs": self.hs,
            "hn24": self.hn24,
            "hn48": self.hn48,
            "hn72": self.hn72,
            "t_air": self.t_air,
            "t_surface": self.t_surface,
            "gust": self.gust,
            "time": self.time,
            "operator": self.operator,
        }


@dataclass
class MappedStation:
    station: Station
    distance_km: float
    weight: float


def flatten(obj, prefix: str = "") -> dict:
    """Flatten nested dicts into {'a.b': value}; lists of dicts are indexed."""
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten(v, f"{prefix}{k}."))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(flatten(v, f"{prefix}{i}."))
    else:
        out[prefix[:-1]] = obj
    return out


def _num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(",", "."))
        except ValueError:
            return None
    return None


def pick(flat: dict, quantity: str, numeric: bool = True):
    for path, value in flat.items():
        last = path.rsplit(".", 1)[-1].lower()
        if last in KEYS[quantity]:
            if numeric:
                n = _num(value)
                if n is not None:
                    return n
            elif value not in (None, ""):
                return str(value)
    return None


def parse_station_feature(feature: dict) -> Station | None:
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates") or []
    if geom.get("type") != "Point" or len(coords) < 2:
        return None
    lon, lat = float(coords[0]), float(coords[1])
    props = feature.get("properties") or {}
    flat = flatten(props)
    elevation = pick(flat, "elevation")
    if elevation is None and len(coords) >= 3:
        elevation = _num(coords[2])
    name = pick(flat, "name", numeric=False) or feature.get("id") or f"{lat:.3f},{lon:.3f}"
    st = Station(name=str(name), lat=lat, lon=lon, elevation=elevation)
    st.hs = pick(flat, "hs")
    st.hn24 = pick(flat, "hn24")
    st.hn48 = pick(flat, "hn48")
    st.hn72 = pick(flat, "hn72")
    st.t_air = pick(flat, "t_air")
    st.t_surface = pick(flat, "t_surface")
    st.gust = pick(flat, "gust")
    st.wind = pick(flat, "wind")
    st.time = pick(flat, "time", numeric=False)
    st.operator = pick(flat, "operator", numeric=False)
    # plausibility
    if st.hs is not None and (st.hs < 0 or st.hs > 800):
        st.hs = None
    for attr in ("hn24", "hn48", "hn72"):
        v = getattr(st, attr)
        if v is not None and (v < 0 or v > 300):
            setattr(st, attr, None)
    return st


def load_stations(http: Http) -> tuple[list[Station], dict]:
    """Return stations and a status dict (property keys seen, counts)."""
    data = http.get_json(config.STATIONS_URL, key="stations.geojson", ttl_s=1800)
    features = data.get("features", []) if isinstance(data, dict) else []
    stations = []
    keys_seen: set[str] = set()
    for f in features:
        props = f.get("properties") or {}
        keys_seen.update(flatten(props).keys())
        st = parse_station_feature(f)
        if st is not None:
            stations.append(st)
    with_hs = sum(1 for s in stations if s.hs is not None)
    status = {
        "count": len(stations),
        "with_hs": with_hs,
        "property_keys": sorted(keys_seen)[:80],
    }
    log.info("stations: %d parsed, %d with snow height; keys: %s", len(stations), with_hs, status["property_keys"])
    return stations, status


def map_stations(resort, stations: list[Station], max_km: float = config.STATION_MAX_KM,
                 max_dz: float = config.STATION_MAX_DZ, max_count: int = config.STATION_MAX_COUNT) -> list[MappedStation]:
    candidates = []
    for st in stations:
        d = haversine_km(resort.lat, resort.lon, st.lat, st.lon)
        if d > max_km:
            continue
        if st.elevation is not None and abs(st.elevation - resort.mid) > max_dz:
            continue
        candidates.append((d, st))
    candidates.sort(key=lambda x: x[0])
    chosen = candidates[:max_count]
    if not chosen:
        return []
    raw = [1.0 / (1.0 + d) for d, _ in chosen]
    total = sum(raw)
    return [MappedStation(station=st, distance_km=round(d, 2), weight=w / total) for (d, st), w in zip(chosen, raw)]


def weighted(mapped: list[MappedStation], attr: str) -> float | None:
    pairs = [(m.weight, getattr(m.station, attr)) for m in mapped if getattr(m.station, attr) is not None]
    if not pairs:
        return None
    total = sum(w for w, _ in pairs)
    return sum(w * v for w, v in pairs) / total
