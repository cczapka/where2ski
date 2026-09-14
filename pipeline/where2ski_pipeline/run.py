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
from .registry import Resort, load_resorts
from .sources.bulletin import fetch_bulletins, fetch_micro_regions, find_micro_region
from .sources.holidays import crowd_factor, fetch_holidays
from .sources.openmeteo import fetch_resort_forecast
from .sources.route import fetch_road_points, road_factor, road_report, waypoints_for
from .sources.smet import fetch_history
from .sources.stations import load_stations, map_stations, weighted

log = logging.getLogger(__name__)


def _md(day: date) -> str:
    return day.strftime("%m-%d")


def is_open(resort: Resort, day: date) -> bool:
    """Season gate from the registry ("MM-DD" open/close, may wrap the year) or sensible defaults."""
    season = resort.season or {}
    default = config.GLACIER_SEASON if resort.glacier else config.DEFAULT_SEASON
    open_md = str(season.get("open") or default[0])[-5:]
    close_md = str(season.get("close") or default[1])[-5:]
    today_md = _md(day)
    if open_md <= close_md:
        return open_md <= today_md <= close_md
    return today_md >= open_md or today_md <= close_md


def assess_resort(resort: Resort, http: Http, today: date, days: list[date], stations, bulletins_by_day,
                  micro_features, holidays, road_points=None) -> dict:
    series = fetch_resort_forecast(http, resort)
    base, mid, top = series["base"], series["mid"], series["top"]

    mapped = map_stations(resort, stations)
    station_hs = weighted(mapped, "hs")
    station_hn = {k: weighted(mapped, k) for k in ("hn24", "hn48", "hn72")} if mapped else None
    my_waypoints = waypoints_for(resort)
    my_roads = [road_points[w[0]] for w in my_waypoints if road_points and w[0] in road_points]
    history = None
    for m in mapped:
        if m.station.data_urls:
            history = fetch_history(http, m.station)
            if history is not None:
                break

    micro = resort.micro_region or find_micro_region(micro_features.get(resort.region, []), resort.lat, resort.lon)
    if micro is None and mapped:
        raw = next((m.station.micro_region for m in mapped if m.station.micro_region), None)
        micro = raw.split()[0] if raw else None  # station feed carries "AT-07-16 Tuxer Alpen Ost"
    # a resort on a border may sit in a micro-region of the neighbouring warning service
    bulletin_region = micro[:5] if micro and micro[:5] in bulletins_by_day else resort.region
    has_bulletin = False

    out_days = []
    for lead, day in enumerate(days):
        level_mid = level_top = None
        avalanche = None
        bulletin = None
        flagged: set[str] = set()
        if micro and lead <= 1:
            for_day = bulletins_by_day.get(bulletin_region, {}).get(day.isoformat()) or {}
            bulletin = for_day.get(micro)
            if bulletin is None and lead == 1:
                bulletin = (bulletins_by_day.get(bulletin_region, {}).get(today.isoformat()) or {}).get(micro)
        if bulletin is not None:
            has_bulletin = True
            for p in bulletin.problems_at(resort.top) + bulletin.problems_at(resort.mid):
                flagged.update(a for a in p.aspects if a in ASPECTS)
            level_mid = bulletin.level_at(resort.mid)
            level_top = bulletin.level_at(resort.top)
            avalanche = {
                "level_mid": level_mid,
                "level_top": level_top,
                "problems": [p.public() for p in bulletin.problems_at(resort.top)],
                "tendency": bulletin.tendency,
                "region": bulletin.region_id,
                "valid": bulletin.valid_date,
                "source": bulletin.source,
            }
        snow = assess_resort_day(mid, top, day, today, resort.aspect_rose, station_hs=station_hs,
                                 station_hn=station_hn, glacier=resort.glacier, history=history,
                                 flagged_aspects=flagged)
        weather = day_weather(base, mid, top, day)
        level = max([lv for lv in (level_mid, level_top) if lv is not None], default=None)
        crowd = crowd_factor(day, holidays)
        roads = road_report(my_roads, day) if my_roads else None
        factors = scoring.build_factors(snow, weather, level, resort.travel_min, crowd,
                                        road_factor(roads, expected=bool(my_waypoints)))
        opened = is_open(resort, day)
        blk = {m: scoring.blockers(m, snow, weather, level, opened) for m in ("freeride", "piste")}
        scores = {m: (0.0 if blk[m] else scoring.score(m, factors)) for m in ("freeride", "piste")}
        out_days.append({
            "date": day.isoformat(),
            "lead": lead,
            "scores": scores,
            "blockers": blk,
            "factors": factors,
            "confidence": scoring.confidence(lead, bool(mapped), has_bulletin),
            "badges": scoring.badges(snow, weather),
            "snow": snow.public(),
            "weather": weather.public(),
            "avalanche": avalanche,
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
    result["days"] = out_days
    result["error"] = None
    return result


def run(registry: Path, out_dir: Path, cache_dir: Path | None = None, offline_dir: Path | None = None,
        today: date | None = None, only: list[str] | None = None) -> dict:
    http = Http(cache_dir=cache_dir, offline_dir=offline_dir)
    resorts = load_resorts(registry)
    if only:
        resorts = [r for r in resorts if r.id in set(only)]
    today = today or datetime.now(ZoneInfo(config.TIMEZONE)).date()
    days = [today + timedelta(days=i) for i in range(config.FORECAST_DAYS)]
    status: dict = {"sources": {}}

    try:
        stations, st_status = load_stations(http)
    except Exception as exc:  # noqa: BLE001
        log.warning("stations unavailable: %s", exc)
        stations, st_status = [], {"error": str(exc)}
    status["sources"]["stations"] = st_status

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
                                         holidays, road_points))
            if results[-1].get("station_history"):
                status["sources"]["station_history"] = status["sources"].get("station_history", 0) + 1
        except Exception as exc:  # noqa: BLE001
            log.error("resort %s failed: %s\n%s", resort.id, exc, traceback.format_exc())
            item = resort.public()
            item.update({"stations": [], "days": [], "error": str(exc)})
            results.append(item)

    latest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
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
    snapshot = {
        "date": today.isoformat(),
        "generated_at": latest["generated_at"],
        "resorts": {r["id"]: {"stations": r.get("stations", []),
                              "today": (r["days"][0] if r.get("days") else None)} for r in results},
    }
    (out_dir / "snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    (out_dir / "index.html").write_text(render_index(latest), encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    return latest


def render_index(latest: dict) -> str:
    """Tiny status page for a browser check of the published data."""
    days = latest["days"]
    rows = []
    for r in sorted(latest["resorts"], key=lambda x: -(x["days"][0]["scores"]["freeride"] if x.get("days") else -1)):
        cells = []
        for d in r.get("days", []):
            f, p = d["scores"]["freeride"], d["scores"]["piste"]
            title = f"{d['snow']['state']} hn24 {d['snow']['hn24']} hs {d['snow']['hs']} sun {d['weather']['sun_hours']}h"
            cells.append(f'<td title="{title}" style="background:hsl({int(f*1.2)},70%,80%)">{f:.0f}<br><small>{p:.0f}</small></td>')
        err = f' <small style="color:#a00">{r["error"]}</small>' if r.get("error") else ""
        rows.append(f"<tr><th style='text-align:left'>{r['name']}{err}</th>{''.join(cells)}</tr>")
    head = "".join(f"<th>{d[5:]}</th>" for d in days)
    return f"""<!doctype html><meta charset="utf-8"><title>where2ski data</title>
<style>body{{font-family:system-ui;margin:16px}}td{{text-align:center;padding:4px 6px;border:1px solid #ddd}}</style>
<h1>where2ski – latest pipeline output</h1>
<p>generated {latest['generated_at']} · <a href="latest.json">latest.json</a> · <a href="resorts.json">resorts.json</a></p>
<p>cells: freeride score / piste score (0–100), hover for details</p>
<table><tr><th></th>{head}</tr>{''.join(rows)}</table>
<p><small>{' · '.join(latest['attribution'])}</small></p>"""
