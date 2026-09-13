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
        if isinstance(vt, dict):
            # bulletins are published the evening before; the end time falls on the day they are valid for
            stamp = vt.get("endTime") or vt.get("startTime")
            if stamp:
                valid = str(stamp)[:10]
        for region in b.get("regions", []) or []:
            rid = region.get("regionID") or region.get("id")
            if rid:
                out[str(rid)] = RegionBulletin(region_id=str(rid), ratings=ratings, problems=problems,
                                               tendency=tendency, valid_date=valid, source=source)
    return out


def parse_ratings(data, source: str, valid_date: str | None = None) -> dict[str, RegionBulletin]:
    """Parse the EAWS aggregation file: {"maxDangerRatings": {"DE-BY-10": 2, "DE-BY-10:pm": 3, ...}}.

    Values are warn-level numbers (0 = no rating). Keys may carry ":am"/":pm"
    (or other) qualifiers; all ratings of a region are kept and level_at()
    returns the maximum, which is the conservative choice.
    """
    out: dict[str, RegionBulletin] = {}
    if isinstance(data, dict) and isinstance(data.get("maxDangerRatings"), dict):
        data = data["maxDangerRatings"]

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

    grouped: dict[str, list[Rating]] = {}
    for key, val in (data.items() if isinstance(data, dict) else []):
        rid, _, qualifier = str(key).partition(":")
        level = to_level(val)
        if level is None:
            continue
        grouped.setdefault(rid, []).append(Rating(level=level, period=qualifier or "all_day"))
    for rid, ratings in grouped.items():
        out[rid] = RegionBulletin(region_id=rid, ratings=ratings, problems=[], tendency=None,
                                  valid_date=valid_date, source=source)
    return out


def _within_a_day(valid_date: str | None, date: str) -> bool:
    if valid_date is None:
        return False
    try:
        from datetime import date as _d
        return abs((_d.fromisoformat(valid_date) - _d.fromisoformat(date)).days) <= 1
    except ValueError:
        return False


def fetch_bulletins(http: Http, region: str, date: str) -> tuple[dict[str, RegionBulletin], dict]:
    """Bulletins valid for ``date`` (YYYY-MM-DD) in ``region``; empty dict if none is available."""
    status = {"region": region, "date": date, "ok": False, "url": None, "error": None, "regions": 0}
    for src in config.BULLETIN_SOURCES.get(region, []):
        url = src["url"].format(date=date)
        kind = src["kind"]
        key = f"eaws_ratings_{date}.json" if kind == "ratings" else f"bulletin_{region}_{date if src['dated'] else 'latest'}.json"
        try:
            data = http.get_json(url, key=key, ttl_s=1800)
        except Exception as exc:  # noqa: BLE001
            status["error"] = f"{url}: {exc}"
            log.warning("bulletin %s failed: %s", url, exc)
            continue
        if kind == "ratings":
            parsed = parse_ratings(data, source=url, valid_date=date)
        else:
            parsed = parse_caaml(data, source=url)
            if src["dated"]:
                for b in parsed.values():
                    b.valid_date = b.valid_date or date
            else:
                stale = {rid: b for rid, b in parsed.items() if not _within_a_day(b.valid_date, date)}
                if stale:
                    sample = next(iter(stale.values())).valid_date
                    log.warning("bulletin %s is stale (valid %s, wanted %s); ignoring", url, sample, date)
                    status["error"] = f"{url}: stale, valid for {sample}"
                    parsed = {rid: b for rid, b in parsed.items() if rid not in stale}
        if parsed:
            status.update(ok=True, url=url, error=None, regions=len(parsed))
            return parsed, status
        status["error"] = status["error"] or f"{url}: no bulletins parsed"
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
