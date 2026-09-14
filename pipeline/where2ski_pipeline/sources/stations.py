"""Weather station observations from the EAWS aggregation used by lawinen.report."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .. import config
from ..geo import haversine_km
from ..http import Http

log = logging.getLogger(__name__)

# Property names of the EAWS station feed (linea listing schema) with the
# conversion into the units used here: cm, °C, km/h. Raw values are SI
# (metres, Kelvin, m/s). Matching is case-insensitive on the last path
# segment, so nested layouts still work.
SPEC = {
    "hs": [("hs", 100.0, 0.0)],
    "hn24": [("hsd_24", 100.0, 0.0)],
    "hn48": [("hsd_48", 100.0, 0.0)],
    "hn72": [("hsd_72", 100.0, 0.0)],
    "t_air": [("ta", 1.0, -273.15)],
    "t_surface": [("tss", 1.0, -273.15)],
    "gust": [("vw_max", 3.6, 0.0)],
    "wind": [("vw", 3.6, 0.0)],
    "elevation": [("altitude", 1.0, 0.0), ("elevation", 1.0, 0.0), ("ele", 1.0, 0.0)],
}
TEXT_KEYS = {
    "name": {"name", "stationname", "station_name", "shortname"},
    "time": {"date", "time", "timestamp", "datetime"},
    "operator": {"operator", "dataproviderid", "provider"},
    "micro_region": {"microregionid", "micro_region", "regionid"},
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
    micro_region: str | None = None
    data_urls: list = field(default_factory=list)

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
            "micro_region": self.micro_region,
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


def pick_number(flat: dict, quantity: str) -> float | None:
    for key, factor, offset in SPEC[quantity]:
        for path, value in flat.items():
            if path.rsplit(".", 1)[-1].lower() == key:
                n = _num(value)
                if n is not None:
                    return n * factor + offset
    return None


def pick_text(flat: dict, quantity: str) -> str | None:
    for path, value in flat.items():
        if path.rsplit(".", 1)[-1].lower() in TEXT_KEYS[quantity] and value not in (None, ""):
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
    elevation = _num(coords[2]) if len(coords) >= 3 else None
    if elevation is None:
        elevation = pick_number(flat, "elevation")
    name = pick_text(flat, "name") or feature.get("id") or f"{lat:.3f},{lon:.3f}"
    st = Station(name=str(name), lat=lat, lon=lon, elevation=elevation)
    st.hs = pick_number(flat, "hs")
    st.hn24 = pick_number(flat, "hn24")
    st.hn48 = pick_number(flat, "hn48")
    st.hn72 = pick_number(flat, "hn72")
    st.t_air = pick_number(flat, "t_air")
    st.t_surface = pick_number(flat, "t_surface")
    st.gust = pick_number(flat, "gust")
    st.wind = pick_number(flat, "wind")
    st.time = pick_text(flat, "time")
    st.operator = pick_text(flat, "operator")
    st.micro_region = pick_text(flat, "micro_region")
    urls = props.get("dataURLs")
    if isinstance(urls, list):
        st.data_urls = [str(u) for u in urls if isinstance(u, str)]
    # plausibility: snow height 0..800 cm; negative height differences mean settling, not new snow
    if st.hs is not None and (st.hs < 0 or st.hs > 800):
        st.hs = None
    for attr in ("hn24", "hn48", "hn72"):
        v = getattr(st, attr)
        if v is not None:
            setattr(st, attr, None if v > 300 else max(0.0, v))
    for attr in ("t_air", "t_surface"):
        v = getattr(st, attr)
        if v is not None and (v < -60 or v > 50):
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
    sample = [s.public() for s in stations if s.hs is not None][:3]
    status = {
        "count": len(stations),
        "with_hs": with_hs,
        "property_keys": sorted(keys_seen)[:80],
        "sample": sample,
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
