"""Forecast verification against station measurements (docs/PLAN.md 6.2).

    python -m tools.verify score --archive DIR [--since 2026-10-15] [--min-mid 1700] [--out out]
    python -m tools.verify backtest --start 2026-10-15 --end 2026-11-15 --archive DIR [--variant api derived]

``score`` needs no network. The observation for target day T is the median
24 h new snow of a resort's stations that passed quality control and were not
stale, read by the first run of day T+1. ``backtest`` refetches hourly
history from the weather service and recomputes daily snowfall with
alternative algorithms, scored against the same observations.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from where2ski_pipeline import config
from where2ski_pipeline.archive import MIDDAY_HOUR_UTC, read_rows
from where2ski_pipeline.model import precip

MIDDAY_END_UTC = 16

THRESHOLDS = (5.0, 15.0)


def _f(v: str):
    return float(v) if v not in ("", None) else None


def observations(obs_rows: list[dict]) -> dict[tuple[str, str], dict]:
    """{(resort, run_date): {"hn24": median, "n": stations, "t_air": [(elev, t)], "t_surface": [..]}} from the
    first observation set of each run date."""
    first: dict[tuple[str, str], str] = {}
    for r in obs_rows:
        k = (r["resort"], r["run_date"])
        first[k] = min(first.get(k, r["run_utc"]), r["run_utc"])
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in obs_rows:
        if r["run_utc"] == first[(r["resort"], r["run_date"])]:
            grouped[(r["resort"], r["run_date"])].append(r)
    out = {}
    for k, rows in grouped.items():
        hn = [_f(r["hn24"]) for r in rows if _f(r["hn24"]) is not None]
        out[k] = {"hn24": statistics.median(hn) if hn else None, "n": len(hn),
                  "t_surface": [_f(r["t_surface"]) for r in rows if _f(r["t_surface"]) is not None]}
    return out


def midday_temperatures(obs_rows: list[dict]) -> dict[tuple[str, str], list[tuple[float, float]]]:
    """{(resort, run_date): [(station elevation, air temperature)]} from observation sets after 11 UTC."""
    out: dict[tuple[str, str], list] = defaultdict(list)
    for r in obs_rows:
        if MIDDAY_HOUR_UTC <= int(r["run_utc"][:2]) < MIDDAY_END_UTC and _f(r["t_air"]) is not None and _f(r["elevation"]) is not None:
            out[(r["resort"], r["run_date"])].append((_f(r["elevation"]), _f(r["t_air"])))
    return out


def contingency(pairs: list[tuple[float, float]], thr: float) -> dict:
    hits = sum(1 for f, o in pairs if f >= thr and o >= thr)
    misses = sum(1 for f, o in pairs if f < thr and o >= thr)
    false = sum(1 for f, o in pairs if f >= thr and o < thr)
    events = hits + misses
    ev = [(f, o) for f, o in pairs if o >= thr]
    random_hits = (hits + false) * events / len(pairs) if pairs else 0.0
    denom = hits + misses + false - random_hits
    return {
        "ets": round((hits - random_hits) / denom, 3) if denom > 0 else None,
        "mean_forecast_on_events_cm": round(statistics.mean(f for f, _ in ev), 1) if ev else None,
        "mean_observed_on_events_cm": round(statistics.mean(o for _, o in ev), 1) if ev else None,
        "threshold_cm": thr, "events": events, "hits": hits, "misses": misses, "false_alarms": false,
        "pod": round(hits / events, 3) if events else None,
        "far": round(false / (hits + false), 3) if hits + false else None,
    }


def skill(pairs: list[tuple[float, float]]) -> dict:
    if not pairs:
        return {"n": 0}
    return {
        "n": len(pairs),
        "mean_forecast_cm": round(statistics.mean(f for f, _ in pairs), 2),
        "mean_observed_cm": round(statistics.mean(o for _, o in pairs), 2),
        "bias_cm": round(statistics.mean(f - o for f, o in pairs), 2),
        "mae_cm": round(statistics.mean(abs(f - o) for f, o in pairs), 2),
        "categories": [contingency(pairs, t) for t in THRESHOLDS],
    }


def _mids(registry: Path) -> dict[str, float]:
    data = json.loads(Path(registry).read_text(encoding="utf-8"))
    return {r["id"]: float(r["elevation"]["mid"]) for r in data["resorts"]}


def score(archive: Path, since: str | None = None, until: str | None = None, min_mid: float = 0.0,
          registry: Path = Path("data/resorts.json"), field: str = "snow_mid_cm") -> dict:
    forecasts = read_rows(archive, "forecast")
    obs_rows = read_rows(archive, "obs")
    obs = observations(obs_rows)
    temps = midday_temperatures(obs_rows)
    mids = _mids(registry)
    by_lead: dict[int, list] = defaultdict(list)
    t_by_lead: dict[int, list] = defaultdict(list)
    plaus = {"corn_or_crust_after_5cm": 0, "lead0_days_with_5cm": 0, "powder_on_melting_surface": 0,
             "lead0_powder_days": 0}
    for r in forecasts:
        target = r["target"]
        if (since and target < since) or (until and target > until) or mids.get(r["resort"], 0) < min_mid:
            continue
        lead = int(r["lead"])
        nxt = (date.fromisoformat(target) + timedelta(days=1)).isoformat()
        o = obs.get((r["resort"], nxt))
        fc = _f(r[field])
        if o and o["hn24"] is not None and fc is not None:
            by_lead[lead].append((fc, o["hn24"]))
        tm = _f(r["t_mid"])
        mid = mids.get(r["resort"])
        near = [t for e, t in temps.get((r["resort"], target), []) if mid is not None and abs(e - mid) <= 250]
        if tm is not None and near:
            t_by_lead[lead].append((tm, statistics.median(near)))
        if lead == 0:
            same = obs.get((r["resort"], target))
            if same and same["hn24"] is not None and same["hn24"] >= 5:
                plaus["lead0_days_with_5cm"] += 1
                plaus["corn_or_crust_after_5cm"] += r["state_mid"] in ("corn", "crust")
            if r["state_mid"] in ("fresh_powder", "settled_powder"):
                plaus["lead0_powder_days"] += 1
                plaus["powder_on_melting_surface"] += bool(same and any(t >= -0.5 for t in same["t_surface"]))
    result = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "filter": {"since": since, "until": until, "min_mid_m": min_mid, "field": field},
        "observation": "median HSD_24 of quality-controlled, fresh stations, first run of the following day",
        "snowfall": {str(k): skill(v) for k, v in sorted(by_lead.items())},
        "temperature_mid": {str(k): {"n": len(v), "bias_c": round(statistics.mean(f - o for f, o in v), 2),
                                     "mae_c": round(statistics.mean(abs(f - o) for f, o in v), 2)}
                            for k, v in sorted(t_by_lead.items()) if v},
        "plausibility": plaus,
    }
    return result


def markdown(result: dict) -> str:
    lines = [f"### Snowfall forecast against stations ({result['filter']})", "",
             "| lead | n | mean fc | mean obs | bias | MAE | ≥5 cm hits/events | POD | FAR | ETS | ≥15 cm hits/events | POD | FAR |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for lead, s in result["snowfall"].items():
        if not s.get("n"):
            continue
        c5, c15 = s["categories"]
        lines.append(f"| {lead} | {s['n']} | {s['mean_forecast_cm']} | {s['mean_observed_cm']} | {s['bias_cm']:+} | "
                     f"{s['mae_cm']} | {c5['hits']}/{c5['events']} | {c5['pod']} | {c5['far']} | {c5['ets']} | "
                     f"{c15['hits']}/{c15['events']} | {c15['pod']} | {c15['far']} |")
    if result["temperature_mid"]:
        lines += ["", "| lead | n | T bias °C | T MAE °C |", "|---|---|---|---|"]
        for lead, t in result["temperature_mid"].items():
            lines.append(f"| {lead} | {t['n']} | {t['bias_c']:+} | {t['mae_c']} |")
    p = result["plausibility"]
    lines += ["", f"Corn or crust on a day with ≥5 cm measured: {p['corn_or_crust_after_5cm']} of "
                  f"{p['lead0_days_with_5cm']}. Powder with a melting surface measured: "
                  f"{p['powder_on_melting_surface']} of {p['lead0_powder_days']}."]
    return "\n".join(lines)


# --- backtest -------------------------------------------------------------------------------------

VARIANTS = {
    "api": lambda h: h["snowfall"] or 0.0,
    "derived": lambda h: precip.snow_cm(h["precipitation"] or 0.0, h["temperature_2m"], h.get("relative_humidity_2m"))[0] or 0.0,
}


def backtest(archive: Path, start: str, end: str, variants: list[str], registry: Path, min_mid: float,
             cache: Path | None = None, points: list[str] = ("registry",), offline: Path | None = None) -> dict:
    """Experiment 7.1: daily mid-band snowfall from the weather service's history, per query point
    (registry point or terrain centroid of the middle third of the runs) and per snowfall algorithm."""
    from where2ski_pipeline.http import Http
    from where2ski_pipeline.registry import load_resorts

    http = Http(cache_dir=None if offline else cache, offline_dir=offline)
    obs = observations(read_rows(archive, "obs"))
    days_back = (date.today() - date.fromisoformat(start)).days + 1
    if days_back > 92:
        raise SystemExit("the weather service keeps 92 past days; choose a later start")
    pairs: dict[str, list] = {f"{pt}/{v}": [] for pt in points for v in variants}
    for resort in load_resorts(registry):
        if resort.mid < min_mid:
            continue
        for pt in points:
            lat, lon, ele = resort.band_point("mid") if pt == "terrain" else (resort.lat, resort.lon, resort.mid)
            params = {"latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}", "elevation": f"{ele:.0f}",
                      "hourly": "temperature_2m,relative_humidity_2m,precipitation,snowfall", "past_days": days_back,
                      "forecast_days": 1, "timezone": config.TIMEZONE, "models": "best_match"}
            data = http.get_json(config.OPEN_METEO_URL, key=f"backtest_{pt}_{resort.id}_{start}.json", params=params,
                                 ttl_s=6 * 3600)
            hourly = data["hourly"]
            daily: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
            for i, t in enumerate(hourly["time"]):
                day = t[:10]
                if not (start <= day <= end) or hourly["temperature_2m"][i] is None:
                    continue
                h = {k: hourly[k][i] for k in hourly if k != "time"}
                for v in variants:
                    daily[day][v] += VARIANTS[v](h)
            for day, sums in daily.items():
                nxt = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
                o = obs.get((resort.id, nxt))
                if o and o["hn24"] is not None:
                    for v in variants:
                        pairs[f"{pt}/{v}"].append((sums[v], o["hn24"]))
    return {"start": start, "end": end, "min_mid_m": min_mid, "variants": {k: skill(p) for k, p in pairs.items()}}


def backtest_markdown(result: dict) -> str:
    lines = [f"### Backtest {result['start']} to {result['end']}, mid band at or above {result['min_mid_m']:.0f} m", "",
             "| query point / snowfall | n | bias | MAE | ≥5 cm hits/events | POD | FAR | ETS | mean fc / obs on events | ≥15 cm hits/events |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for k, s in result["variants"].items():
        if not s.get("n"):
            lines.append(f"| {k} | 0 | | | | | | | | |")
            continue
        c5, c15 = s["categories"]
        lines.append(f"| {k} | {s['n']} | {s['bias_cm']:+} | {s['mae_cm']} | {c5['hits']}/{c5['events']} | {c5['pod']} | "
                     f"{c5['far']} | {c5['ets']} | {c5['mean_forecast_on_events_cm']} / {c5['mean_observed_on_events_cm']} | "
                     f"{c15['hits']}/{c15['events']} |")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="verify")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score")
    s.add_argument("--archive", type=Path, required=True)
    s.add_argument("--since")
    s.add_argument("--until")
    s.add_argument("--min-mid", type=float, default=0.0)
    s.add_argument("--registry", type=Path, default=Path("data/resorts.json"))
    s.add_argument("--out", type=Path)
    b = sub.add_parser("backtest")
    b.add_argument("--archive", type=Path, required=True)
    b.add_argument("--start", required=True)
    b.add_argument("--end", required=True)
    b.add_argument("--variant", nargs="+", default=list(VARIANTS), choices=list(VARIANTS))
    b.add_argument("--min-mid", type=float, default=0.0)
    b.add_argument("--registry", type=Path, default=Path("data/resorts.json"))
    b.add_argument("--cache", type=Path, default=Path("cache"))
    b.add_argument("--points", nargs="+", default=["registry", "terrain"], choices=["registry", "terrain"])
    b.add_argument("--offline", type=Path, help="replay recorded responses instead of fetching")
    b.add_argument("--out", type=Path)
    args = ap.parse_args(argv)

    if args.cmd == "score":
        result = score(args.archive, args.since, args.until, args.min_mid, args.registry)
        text = markdown(result)
    else:
        result = backtest(args.archive, args.start, args.end, args.variant, args.registry, args.min_mid, args.cache,
                          args.points, args.offline)
        text = backtest_markdown(result)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    if getattr(args, "out", None):
        args.out.mkdir(parents=True, exist_ok=True)
        name = "verification.json" if args.cmd == "score" else "backtest.json"
        (args.out / name).write_text(json.dumps(result, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
