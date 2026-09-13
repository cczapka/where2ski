"""Avalanche bulletins (CAAML v6 JSON) and warning micro-regions."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .. import config
from ..geo import point_in_geometry
from ..http import Http

log = logging.getLogger(__name__)

LEVELS = {"low": 1, "moderate": 2, "considerable": 3, "high": 4, "very_high": 5, "no_rating": None, "no_snow": None}


@dataclass
class Rating:
    level: int | None
    lower: float | None = None  # applies above this elevation (m)
    upper: float | None = None  # applies below this elevation (m)
    period: str = "all_day"


@dataclass
class Problem:
    type: str
    aspects: list[str] = field(default_factory=list)
    lower: float | None = None
    upper: float | None = None
    period: str = "all_day"

    def public(self) -> dict:
        elev = ""
        if self.lower is not None and self.upper is not None:
            elev = f"{self.lower:.0f}–{self.upper:.0f} m"
        elif self.lower is not None:
            elev = f"above {self.lower:.0f} m"
        elif self.upper is not None:
            elev = f"below {self.upper:.0f} m"
        return {"type": self.type, "aspects": self.aspects, "elevation": elev, "period": self.period}


@dataclass
class RegionBulletin:
    region_id: str
    ratings: list[Rating]
    problems: list[Problem]
    tendency: str | None
    valid_date: str | None
    source: str

    def level_at(self, elevation: float) -> int | None:
        best = None
        for r in self.ratings:
            if r.level is None:
                continue
            if r.lower is not None and elevation < r.lower:
                continue
            if r.upper is not None and elevation > r.upper:
                continue
            if best is None or r.level > best:
                best = r.level
        return best

    def problems_at(self, elevation: float) -> list[Problem]:
        out = []
        for p in self.problems:
            if p.lower is not None and elevation < p.lower:
                continue
            if p.upper is not None and elevation > p.upper:
                continue
            out.append(p)
        return out


def _elev(obj: dict | None) -> tuple[float | None, float | None]:
    if not obj:
        return None, None

    def num(v):
        if v in (None, ""):
            return None
        try:
            return float(str(v).replace("m", "").strip())
        except ValueError:
            return None

    return num(obj.get("lowerBound")), num(obj.get("upperBound"))


def parse_caaml(data: dict, source: str) -> dict[str, RegionBulletin]:
    out: dict[str, RegionBulletin] = {}
    bulletins = data.get("bulletins") if isinstance(data, dict) else None
    if bulletins is None and isinstance(data, list):
        bulletins = data
    for b in bulletins or []:
        ratings = []
        for r in b.get("dangerRatings", []) or []:
            lower, upper = _elev(r.get("elevation"))
            ratings.append(Rating(level=LEVELS.get(str(r.get("mainValue", "")).lower()), lower=lower, upper=upper,
                                  period=r.get("validTimePeriod", "all_day") or "all_day"))
        problems = []
        for p in b.get("avalancheProblems", []) or []:
            lower, upper = _elev(p.get("elevation"))
            problems.append(Problem(type=str(p.get("problemType", "unknown")), aspects=list(p.get("aspects", []) or []),
                                    lower=lower, upper=upper, period=p.get("validTimePeriod", "all_day") or "all_day"))
        tendency = None
        t = b.get("tendency")
        if isinstance(t, list) and t:
            tendency = t[0].get("tendencyType")
        elif isinstance(t, dict):
            tendency = t.get("tendencyType")
        valid = None
        vt = b.get("validTime") or {}
        if isinstance(vt, dict) and vt.get("startTime"):
            valid = str(vt["startTime"])[:10]
        for region in b.get("regions", []) or []:
            rid = region.get("regionID") or region.get("id")
            if rid:
                out[str(rid)] = RegionBulletin(region_id=str(rid), ratings=ratings, problems=problems,
                                               tendency=tendency, valid_date=valid, source=source)
    return out


def parse_ratings(data, source: str) -> dict[str, RegionBulletin]:
    """Best-effort parser for EAWS '.ratings.json' aggregation files."""
    out: dict[str, RegionBulletin] = {}

    def to_level(v):
        if isinstance(v, bool):
            return None
        if isinstance(v, (int, float)):
            return int(v) if 1 <= v <= 5 else None
        if isinstance(v, str):
            if v.isdigit():
                return to_level(int(v))
            return LEVELS.get(v.lower())
        return None

    items = data.items() if isinstance(data, dict) else []
    for rid, val in items:
        level = to_level(val)
        ratings = []
        if level is not None:
            ratings.append(Rating(level=level))
        elif isinstance(val, dict):
            for k, v in val.items():
                lv = to_level(v)
                if lv is not None:
                    ratings.append(Rating(level=lv, period=str(k)))
                elif isinstance(v, dict):
                    for kk, vv in v.items():
                        lv2 = to_level(vv)
                        if lv2 is not None:
                            ratings.append(Rating(level=lv2, period=f"{k}/{kk}"))
        if ratings:
            out[str(rid)] = RegionBulletin(region_id=str(rid), ratings=ratings, problems=[], tendency=None,
                                           valid_date=None, source=source)
    return out


def fetch_bulletins(http: Http, region: str, date: str) -> tuple[dict[str, RegionBulletin], dict]:
    status = {"region": region, "ok": False, "url": None, "error": None, "regions": 0}
    for template in config.BULLETIN_CANDIDATES.get(region, []):
        url = template.format(date=date)
        try:
            data = http.get_json(url, key=f"bulletin_{region}.json", ttl_s=1800)
        except Exception as exc:  # noqa: BLE001
            status["error"] = f"{url}: {exc}"
            log.warning("bulletin %s failed: %s", url, exc)
            continue
        parsed = parse_caaml(data, source=url)
        if not parsed and url.endswith(".ratings.json"):
            parsed = parse_ratings(data, source=url)
        if parsed:
            status.update(ok=True, url=url, error=None, regions=len(parsed))
            return parsed, status
        status["error"] = f"{url}: no bulletins parsed"
    return {}, status


def fetch_micro_regions(http: Http, region: str) -> list[dict]:
    url = config.MICRO_REGIONS_URL.format(region=region)
    try:
        data = http.get_json(url, key=f"micro_regions_{region}.json", ttl_s=30 * 86400)
    except Exception as exc:  # noqa: BLE001
        log.warning("micro-regions %s failed: %s", region, exc)
        return []
    return data.get("features", []) if isinstance(data, dict) else []


def find_micro_region(features: list[dict], lat: float, lon: float) -> str | None:
    for f in features:
        if point_in_geometry(lon, lat, f.get("geometry")):
            props = f.get("properties") or {}
            for key in ("id", "regionID", "region_id", "ID"):
                if props.get(key):
                    return str(props[key])
            if f.get("id"):
                return str(f["id"])
    return None
