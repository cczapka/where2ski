"""Weather station observations from the EAWS aggregation used by lawinen.report."""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

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
    age_h: float | None = None
    stale: bool = False
    rejected: list = field(default_factory=list)  # [{"field", "value", "rule"}], why a reading is not used

    def usable(self) -> bool:
        return any(getattr(self, f) is not None for f in ("hs", "hn24", "t_air", "t_surface"))

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
            "age_h": None if self.age_h is None else round(self.age_h, 1),
            "stale": self.stale,
            "rejected": list(self.rejected),
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


VALUE_FIELDS = ("hs", "hn24", "hn48", "hn72", "t_air", "t_surface", "gust", "wind")
SNOW_FIELDS = ("hs", "hn24", "hn48", "hn72")


def parse_time(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        t = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def reject(st: Station, fields, rule: str) -> None:
    """Move readings out of use, keeping what was dropped and why."""
    for f in fields:
        v = getattr(st, f)
        if v is not None:
            st.rejected.append({"field": f, "value": round(float(v), 1), "rule": rule})
            setattr(st, f, None)


def mark_age(stations: list[Station], now: datetime, max_age_h: float = config.STATION_MAX_AGE_H) -> None:
    """Readings older than max_age_h (or without a time) are not used: the feed has frozen for days unnoticed."""
    for st in stations:
        t = parse_time(st.time)
        st.age_h = None if t is None else (now - t).total_seconds() / 3600.0
        if st.age_h is None or st.age_h > max_age_h:
            st.stale = True
            reject(st, VALUE_FIELDS, "stale")


def dedupe(stations: list[Station]) -> list[Station]:
    """Some providers list a station twice (values at one time, an empty record at another). Keep the richer one."""
    best: dict[tuple, Station] = {}
    order = []
    for st in stations:
        key = (st.name, round(st.lat, 4), round(st.lon, 4))
        filled = sum(getattr(st, f) is not None for f in VALUE_FIELDS)
        rank = (filled, st.time or "")
        if key not in best:
            order.append(key)
            best[key] = st
        else:
            cur = best[key]
            if rank > (sum(getattr(cur, f) is not None for f in VALUE_FIELDS), cur.time or ""):
                best[key] = st
    return [best[k] for k in order]


def load_stations(http: Http, now: datetime | None = None) -> tuple[list[Station], dict]:
    """Return stations and a status dict (property keys seen, counts, reading ages)."""
    now = now or datetime.now(timezone.utc)
    # never cached: runs are three hours apart, and a frozen feed must not be mistaken for our own cache
    data = http.get_json(config.STATIONS_URL, key="stations.geojson", ttl_s=0)
    features = data.get("features", []) if isinstance(data, dict) else []
    stations = []
    keys_seen: set[str] = set()
    for f in features:
        props = f.get("properties") or {}
        keys_seen.update(flatten(props).keys())
        st = parse_station_feature(f)
        if st is not None:
            stations.append(st)
    stations = dedupe(stations)
    with_values = [s for s in stations if s.usable()]
    mark_age(stations, now)
    ages = [s.age_h for s in with_values if s.age_h is not None]
    stale = sum(1 for s in with_values if s.stale)
    with_hs = sum(1 for s in stations if s.hs is not None)
    status = {
        "count": len(stations),
        "with_hs": with_hs,
        "median_age_h": round(statistics.median(ages), 2) if ages else None,
        "stale_share": round(stale / len(with_values), 3) if with_values else None,
        "last_modified": http.last_modified.get("stations.geojson"),
        "property_keys": sorted(keys_seen)[:80],
        "sample": [s.public() for s in stations if s.hs is not None][:3],
    }
    log.info("stations: %d parsed, %d with snow height, median age %s h, stale share %s, Last-Modified %s",
             len(stations), with_hs, status["median_age_h"], status["stale_share"], status["last_modified"])
    return stations, status


def map_stations(resort, stations: list[Station], max_km: float = config.STATION_MAX_KM,
                 max_dz: float = config.STATION_MAX_DZ, max_count: int = config.STATION_MAX_COUNT,
                 band_elevation: float | None = None) -> list[MappedStation]:
    band = resort.mid if band_elevation is None else band_elevation
    candidates = []
    for st in stations:
        d = haversine_km(resort.lat, resort.lon, st.lat, st.lon)
        if d > max_km:
            continue
        if band_elevation is not None and st.elevation is None:
            continue
        if st.elevation is not None and abs(st.elevation - band) > max_dz:
            continue
        candidates.append((d, st))
    # stations with readings first, so empty or stale ones only fill free slots
    candidates.sort(key=lambda x: (not x[1].usable(), x[0]))
    chosen = candidates[:max_count]
    if not chosen:
        return []
    raw = [1.0 / (1.0 + d) for d, _ in chosen]
    total = sum(raw)
    return [MappedStation(station=st, distance_km=round(d, 2), weight=w / total) for (d, st), w in zip(chosen, raw)]


def quality_control(mapped: list[MappedStation], yesterday_hs: dict | None = None,
                    precip_24h_mm: float | None = None, model_depth_cm: float | None = None,
                    exclude=()) -> list[MappedStation]:
    """Drop implausible readings for one resort. Works on copies: stations are shared between resorts."""
    out = [MappedStation(station=replace(m.station, rejected=list(m.station.rejected)), distance_km=m.distance_km,
                         weight=m.weight) for m in mapped]
    stations = [m.station for m in out]
    for st in stations:
        if st.name in set(exclude):
            reject(st, VALUE_FIELDS, "excluded")
        if st.hs is not None and not (0.0 <= st.hs <= config.QC_HS_MAX_CM):
            reject(st, SNOW_FIELDS, "limit")
        if st.hn24 is not None and st.hn24 > config.QC_HN24_MAX_CM:
            reject(st, SNOW_FIELDS, "limit_24h")
    for st in stations:
        if st.hn24 is not None and st.hn24 > config.QC_HN24_CONFIRM_CM:
            confirmed = any(o is not st and o.hn24 is not None and o.hn24 >= config.QC_HN24_SUPPORT_CM
                            for o in stations)
            if not confirmed:
                reject(st, SNOW_FIELDS, "agreement")
    for st in stations:
        before = (yesterday_hs or {}).get(st.name)
        if st.hs is not None and before is not None and abs(st.hs - before) > config.QC_HS_JUMP_CM:
            if precip_24h_mm is None or precip_24h_mm < config.QC_JUMP_PRECIP_MM:
                reject(st, SNOW_FIELDS, "continuity")
    for st in stations:
        if (st.hs is not None and 0 < st.hs < config.QC_BARE_HS_CM and st.t_air is not None
                and st.t_air > config.QC_BARE_T_AIR and model_depth_cm is not None and model_depth_cm <= 0.0):
            st.rejected.append({"field": "hs", "value": round(st.hs, 1), "rule": "bare_ground"})
            st.hs = 0.0
    return out


def combine(mapped: list[MappedStation], attr: str) -> float | None:
    """Robust value of several stations: median of three or more; of two the mean, or the lower one
    when they differ by more than a factor of two."""
    vals = [float(getattr(m.station, attr)) for m in mapped if getattr(m.station, attr) is not None]
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    if len(vals) == 2:
        lo, hi = sorted(vals)
        return lo if hi > 2.0 * lo else (lo + hi) / 2.0
    return float(statistics.median(vals))


def weighted(mapped: list[MappedStation], attr: str) -> float | None:
    pairs = [(m.weight, getattr(m.station, attr)) for m in mapped if getattr(m.station, attr) is not None]
    if not pairs:
        return None
    total = sum(w for w, _ in pairs)
    return sum(w * v for w, v in pairs) / total
