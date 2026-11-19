"""Orchestration: fetch sources, assess every resort and day, write JSON outputs."""

from __future__ import annotations

import json
import logging
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import __version__, config
from .http import Http
from .model import score as scoring
from .model.snow import ASPECTS, assess_resort_day, day_weather
from .model.surface import simulate_resort
from .registry import Resort, load_resorts
from .sources.bulletin import fetch_bulletins, fetch_micro_regions, find_micro_region
from .sources.holidays import crowd_factor, fetch_holidays
from .sources.openmeteo import fetch_resort_forecast
from .sources.route import fetch_road_points, road_factor, road_report, waypoints_for
from .sources.smet import fetch_history
from .archive import write_archive, yesterday_hs
from .sources.stations import combine, load_stations, map_stations, quality_control

log = logging.getLogger(__name__)


def _md(day: date) -> str:
    return day.strftime("%m-%d")


def _as_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value and len(str(value)) == 10 else None
    except ValueError:
        return None


def is_open(resort: Resort, day: date) -> bool:
    """Season gate from the registry or sensible defaults.

    ``open``/``close`` are either full dates of the current season ("2026-11-27") or
    "MM-DD" for every year, which may wrap the year end.
    """
    season = resort.season or {}
    default = config.GLACIER_SEASON if resort.glacier else config.DEFAULT_SEASON
    o, c = _as_date(season.get("open")), _as_date(season.get("close"))
    if o and c:
        return o <= day <= c
    open_md = str(season.get("open") or default[0])[-5:]
    close_md = str(season.get("close") or default[1])[-5:]
    today_md = _md(day)
    if open_md <= close_md:
        return open_md <= today_md <= close_md
    return today_md >= open_md or today_md <= close_md


def is_limited(resort: Resort, day: date) -> bool:
    """Open with a few lifts only, between the season start and ``limited_until``."""
    until = _as_date((resort.season or {}).get("limited_until"))
    return until is not None and is_open(resort, day) and day <= until


def band_shares(resort: Resort) -> dict:
    """Weights of the mid and top band in the surface value: their share of run length (tools/terrain.py)."""
    share = (resort.terrain or {}).get("band_share") or {}
    m, t = float(share.get("mid") or 0.0), float(share.get("top") or 0.0)
    return {"mid": m / (m + t), "top": t / (m + t)} if m + t > 0 else {"mid": 0.5, "top": 0.5}


def glacier_depth_station(resort: Resort, stations) -> object | None:
    """A snow-depth station near the top band, for the off-piste rule on glaciers."""
    mapped = map_stations(resort, stations, max_dz=config.GLACIER_STATION_MAX_DZ, max_count=5,
                          band_elevation=resort.top)
    with_hs = [m for m in mapped if m.station.hs is not None]
    return with_hs[0] if with_hs else None


def assess_resort(resort: Resort, http: Http, today: date, days: list[date], stations, bulletins_by_day,
                  micro_features, holidays, road_points=None, yesterday: dict | None = None,
                  now: datetime | None = None, bulletin_status: dict | None = None) -> dict:
    series = fetch_resort_forecast(http, resort)
    base, mid, top = series["base"], series["mid"], series["top"]

    now_local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(config.TIMEZONE)).replace(tzinfo=None)
    day_start = datetime.combine(today, datetime.min.time())
    precip_24h = sum(v for v in mid.slice("precipitation", now_local - timedelta(hours=24), now_local) if v is not None)
    depth = [v for v in mid.slice("snow_depth", day_start, day_start + timedelta(days=1)) if v is not None]
    model_depth_cm = 100.0 * sum(depth) / len(depth) if depth else None
    mapped = quality_control(map_stations(resort, stations), yesterday_hs=yesterday,
                             precip_24h_mm=precip_24h, model_depth_cm=model_depth_cm,
                             exclude=resort.links.get("exclude_stations") or ())
    station_hs = combine(mapped, "hs")
    station_hn = {k: combine(mapped, k) for k in ("hn24", "hn48", "hn72")} if mapped else None
    if station_hn is not None and all(v is None for v in station_hn.values()):
        station_hn = None
    glacier_station = None
    if resort.glacier:
        top_mapped = glacier_depth_station(resort, stations)
        if top_mapped is not None:
            glacier_station = quality_control([top_mapped], yesterday_hs=yesterday, precip_24h_mm=precip_24h)[0]
            if glacier_station.station.hs is None:
                glacier_station = None
    my_waypoints = waypoints_for(resort)
    my_roads = [road_points[w[0]] for w in my_waypoints if road_points and w[0] in road_points]
    history = None
    for m in mapped:
        if m.station.data_urls:
            history = fetch_history(http, m.station)
            if history is not None:
                break

    surface_sims = simulate_resort(mid, top, resort.lat, resort.lon, history=history, now=now_local)
    band_weights = band_shares(resort)

    micro = resort.micro_region or find_micro_region(micro_features.get(resort.region, []), resort.lat, resort.lon)
    if micro is None and mapped:
        raw = next((m.station.micro_region for m in mapped if m.station.micro_region), None)
        micro = raw.split()[0] if raw else None  # station feed carries "AT-07-16 Tuxer Alpen Ost"
    # a resort on a border may sit in a micro-region of the neighbouring warning service
    bulletin_region = micro[:5] if micro and micro[:5] in bulletins_by_day else resort.region
    region_status = (bulletin_status or {}).get(bulletin_region, [])
    today_bulletin = (bulletins_by_day.get(bulletin_region, {}).get(today.isoformat()) or {}).get(micro) if micro else None
    has_bulletin = False

    out_days = []
    for lead, day in enumerate(days):
        level_mid = level_top = None
        avalanche = None
        bulletin = None
        flagged: set[str] = set()
        reason = "bulletin"
        if micro:
            bulletin = (bulletins_by_day.get(bulletin_region, {}).get(day.isoformat()) or {}).get(micro)
        if bulletin is None and lead >= 1 and today_bulletin is not None:
            bulletin, reason = today_bulletin, "beyond_bulletin"
        if bulletin is not None:
            has_bulletin = True
            for p in bulletin.problems_at(resort.top) + bulletin.problems_at(resort.mid):
                flagged.update(a for a in p.aspects if a in ASPECTS)
            level_mid = bulletin.level_at(resort.mid)
            level_top = bulletin.level_at(resort.top)
            if reason == "beyond_bulletin" and bulletin.tendency == "increasing":
                level_mid = None if level_mid is None else min(5, level_mid + 1)
                level_top = None if level_top is None else min(5, level_top + 1)
            avalanche = {
                "level_mid": level_mid,
                "level_top": level_top,
                "problems": [p.public() for p in bulletin.problems_at(resort.top)],
                "tendency": bulletin.tendency,
                "region": bulletin.region_id,
                "valid": bulletin.valid_date,
                "source": bulletin.source,
                "carried_forward": reason == "beyond_bulletin",
            }
            if level_mid is None and level_top is None:
                reason = "no_rating"
        else:
            today_status = region_status[0] if region_status else {}
            if not micro:
                reason = "no_rating"
            elif today_status.get("reason") == "failed":
                reason = "fetch_failed"
            elif today_status.get("ok"):
                reason = "no_rating"  # bulletin published, but not for this micro-region
            else:
                reason = "out_of_season"
        snow = assess_resort_day(mid, top, day, today, resort.aspect_rose, station_hs=station_hs,
                                 station_hn=station_hn, glacier=resort.glacier, history=history,
                                 flagged_aspects=flagged, surface_sims=surface_sims, band_weights=band_weights)
        if resort.glacier and snow.hs is not None and snow.hs < config.BASE_MIN_PISTE:
            snow.value_piste = round(snow.value_piste * config.GLACIER_THIN_PISTE_FACTOR, 3)
            snow.reasons.append("thin cover over glacier ice")
        glacier_top_hs = None
        if glacier_station is not None:
            glacier_top_hs = glacier_station.station.hs
            if day > today:  # carried forward with forecast snowfall at the top, settled
                noon = datetime.combine(day, datetime.min.time()) + timedelta(hours=12)
                glacier_top_hs += 0.7 * sum(v for v in top.slice("snowfall", day_start + timedelta(hours=12), noon)
                                            if v is not None)
        weather = day_weather(base, mid, top, day)
        level = max([lv for lv in (level_mid, level_top) if lv is not None], default=None)
        crowd = crowd_factor(day, holidays)
        roads = road_report(my_roads, day) if my_roads else None
        factors = scoring.build_factors(snow, weather, level, resort.travel_min, crowd,
                                        road_factor(roads, expected=bool(my_waypoints)), avalanche_reason=reason)
        opened = is_open(resort, day)
        limited = is_limited(resort, day)
        blk = {m: scoring.blockers(m, snow, weather, level, opened, glacier=resort.glacier,
                                   mid_elevation=resort.mid, glacier_top_hs=glacier_top_hs)
               for m in ("freeride", "piste")}
        scores = {m: (0.0 if blk[m] else scoring.score(m, factors)) for m in ("freeride", "piste")}
        if limited and not blk["piste"]:
            scores["piste"] = round(scores["piste"] * config.LIMITED_OPENING_PISTE, 1)
        out_days.append({
            "date": day.isoformat(),
            "lead": lead,
            "scores": scores,
            "blockers": blk,
            "factors": factors,
            "confidence": scoring.confidence(lead, bool(mapped), bulletin is not None and reason != "no_rating",
                                             reason),
            "badges": scoring.badges(snow, weather) + (["limited_opening"] if limited else []),
            "snow": snow.public(),
            "weather": weather.public(),
            "avalanche": avalanche,
            "avalanche_reason": reason,
            "avalanche_note": scoring.AVALANCHE_NOTES.get(reason),
            "limited_opening": limited,
            "glacier_top_hs": None if glacier_top_hs is None else round(glacier_top_hs),
            "roads": roads,
        })

    result = resort.public()
    result["micro_region"] = micro
    result["station_history"] = None if history is None else {
        "station": history.station, "from": history.start.isoformat(timespec="minutes") if history.start else None,
        "to": history.end.isoformat(timespec="minutes") if history.end else None,
        "has_tss": any(v is not None for v in history.values.get("TSS", [])),
    }
    result["stations"] = [
        {**m.station.public(), "distance_km": m.distance_km, "weight": round(m.weight, 2)} for m in mapped
    ]
    result["glacier_station"] = None if glacier_station is None else {
        **glacier_station.station.public(), "distance_km": glacier_station.distance_km}
    result["days"] = out_days
    result["error"] = None
    return result


SCHEMA_VERSION = 2
RUN_META = "_run.json"  # written next to recorded responses so a replay uses the same clock


def run(registry: Path, out_dir: Path, cache_dir: Path | None = None, offline_dir: Path | None = None,
        today: date | None = None, only: list[str] | None = None, record_dir: Path | None = None,
        now: datetime | None = None, archive_dir: Path | None = None) -> dict:
    http = Http(cache_dir=cache_dir, offline_dir=offline_dir, record_dir=record_dir)
    resorts = load_resorts(registry)
    if only:
        resorts = [r for r in resorts if r.id in set(only)]
    recorded = {}
    if offline_dir is not None and (Path(offline_dir) / RUN_META).exists():
        recorded = json.loads((Path(offline_dir) / RUN_META).read_text(encoding="utf-8"))
        http.last_modified.update(recorded.get("last_modified", {}))
    if now is None:
        now = datetime.fromisoformat(recorded["now"]) if recorded.get("now") else datetime.now(timezone.utc)
    if today is None:
        today = date.fromisoformat(recorded["today"]) if recorded.get("today") else \
            now.astimezone(ZoneInfo(config.TIMEZONE)).date()
    days = [today + timedelta(days=i) for i in range(config.FORECAST_DAYS)]
    status: dict = {"sources": {}, "warnings": []}

    try:
        stations, st_status = load_stations(http, now=now)
    except Exception as exc:  # noqa: BLE001
        log.warning("stations unavailable: %s", exc)
        stations, st_status = [], {"error": str(exc)}
        status["warnings"].append("Station data could not be loaded: measured snow is missing.")
    status["sources"]["stations"] = st_status
    if (st_status.get("stale_share") or 0) > config.STALE_WARNING_SHARE:
        status["warnings"].append(
            f"Station data is stale: {st_status['stale_share']:.0%} of stations have not reported for more than "
            f"{config.STATION_MAX_AGE_H:.0f} h (median age {st_status['median_age_h']} h). Measured snow is not used.")
    yesterday = yesterday_hs(archive_dir, today)

    regions = sorted({r.region for r in resorts})
    bulletins_by_day: dict = {}
    micro_features = {}
    status["sources"]["bulletins"] = {}
    for region in regions:
        bulletins_by_day[region] = {}
        status["sources"]["bulletins"][region] = []
        for day in days[:2]:
            parsed, b_status = fetch_bulletins(http, region, day.isoformat())
            bulletins_by_day[region][day.isoformat()] = parsed
            status["sources"]["bulletins"][region].append(b_status)
        if status["sources"]["bulletins"][region][0].get("reason") == "failed":
            status["warnings"].append(f"The avalanche bulletin for {region} could not be loaded.")
        micro_features[region] = fetch_micro_regions(http, region)
        status["sources"].setdefault("micro_regions", {})[region] = len(micro_features[region])

    holidays, h_status = fetch_holidays(http, days[0], days[-1])
    status["sources"]["holidays"] = h_status

    try:
        road_points = fetch_road_points(http, resorts)
    except Exception as exc:  # noqa: BLE001
        log.warning("road forecast unavailable: %s", exc)
        road_points = {}
    status["sources"]["roads"] = {"waypoints": sorted(road_points)}

    results = []
    for resort in resorts:
        try:
            results.append(assess_resort(resort, http, today, days, stations, bulletins_by_day, micro_features,
                                         holidays, road_points, yesterday=yesterday.get(resort.id), now=now,
                                         bulletin_status=status["sources"]["bulletins"]))
            if results[-1].get("station_history"):
                status["sources"]["station_history"] = status["sources"].get("station_history", 0) + 1
        except Exception as exc:  # noqa: BLE001
            log.error("resort %s failed: %s\n%s", resort.id, exc, traceback.format_exc())
            item = resort.public()
            item.update({"stations": [], "days": [], "error": str(exc)})
            results.append(item)

    latest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "pipeline_version": __version__,
        "today": today.isoformat(),
        "days": [d.isoformat() for d in days],
        "home": config.HOME,
        "weights": config.WEIGHTS,
        "attribution": config.ATTRIBUTION,
        "status": status,
        "resorts": results,
    }

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "latest.json").write_text(json.dumps(latest, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "resorts.json").write_text(
        json.dumps({"resorts": [r.public() for r in resorts]}, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "index.html").write_text(render_index(latest), encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    if archive_dir is not None:
        status["archive"] = write_archive(Path(archive_dir), latest, now)
        (out_dir / "latest.json").write_text(json.dumps(latest, ensure_ascii=False, indent=1), encoding="utf-8")
    if record_dir is not None:
        meta = {"now": now.isoformat(), "today": today.isoformat(), "last_modified": http.last_modified}
        (Path(record_dir) / RUN_META).write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return latest


def render_index(latest: dict) -> str:
    """Deliberately empty and not indexed: the data is for the app, not for visitors or search engines."""
    return """<!doctype html><meta charset="utf-8"><meta name="robots" content="noindex, nofollow, noarchive">
<title>.</title>"""
