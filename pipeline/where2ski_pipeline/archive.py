"""Append-only forecast and observation archive (docs/PLAN.md 6.1).

Two CSV files per month live in the archive directory, which CI checks out
from the ``data`` branch:

- ``forecast-YYYY-MM.csv``: one row per run date, resort and target day, all ten lead days.
- ``obs-YYYY-MM.csv``: one row per run, resort and mapped station, with the reading's age
  and every value quality control rejected.

Forecast rows are written once a day by the first run after FORECAST_HOUR_UTC, so the
weather model's base time is the same every day. Observations are written by that run
and again by the first run after MIDDAY_HOUR_UTC, for daytime temperatures.
"""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

FORECAST_HOUR_UTC = 5
MIDDAY_HOUR_UTC = 11

FORECAST_FIELDS = [
    "run_date", "resort", "target", "lead", "snow_base_cm", "snow_mid_cm", "snow_top_cm", "precip_mm",
    "snow_line_m", "t_mid", "sun_h", "gust_top", "state_mid", "new_on_top_cm", "hs", "hs_source",
    "score_freeride", "score_piste", "confidence",
]
# run_utc is not in the plan's list: it tells the morning and the midday observation sets apart
OBS_FIELDS = [
    "run_date", "run_utc", "resort", "station", "elevation", "obs_time", "age_h", "hs", "hn24", "hn48", "hn72",
    "t_air", "t_surface", "gust", "rejected",
]


def _month_file(archive_dir: Path, kind: str, day: str) -> Path:
    return Path(archive_dir) / f"{kind}-{day[:7]}.csv"


def _fmt(v, nd=1):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def format_rejected(rejected: list) -> str:
    return ";".join(f"{r['field']}={r['value']}:{r['rule']}" for r in rejected or [])


def parse_rejected(text: str) -> list[dict]:
    out = []
    for part in (text or "").split(";"):
        if not part:
            continue
        field, _, rest = part.partition("=")
        value, _, rule = rest.rpartition(":")
        out.append({"field": field, "value": float(value) if value else None, "rule": rule})
    return out


def read_rows(archive_dir: Path | None, kind: str, months: list[str] | None = None) -> list[dict]:
    if archive_dir is None or not Path(archive_dir).exists():
        return []
    files = sorted(Path(archive_dir).glob(f"{kind}-*.csv"))
    if months is not None:
        files = [f for f in files if f.stem.split("-", 1)[1] in months]
    rows: list[dict] = []
    for f in files:
        with f.open(newline="", encoding="utf-8") as fh:
            rows.extend(csv.DictReader(fh))
    return rows


def yesterday_hs(archive_dir: Path | None, today: date) -> dict[str, dict[str, float]]:
    """{resort: {station: snow height}} from the last observation set of the previous day."""
    day = (today - timedelta(days=1)).isoformat()
    rows = [r for r in read_rows(archive_dir, "obs", [day[:7]]) if r["run_date"] == day]
    last = max((r["run_utc"] for r in rows), default=None)
    out: dict[str, dict[str, float]] = {}
    for r in rows:
        if r["run_utc"] == last and r["hs"] != "":
            out.setdefault(r["resort"], {})[r["station"]] = float(r["hs"])
    return out


def _append(path: Path, fields: list[str], rows: list[dict]) -> int:
    if not rows:
        return 0
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        if new:
            w.writeheader()
        w.writerows(rows)
    return len(rows)


def forecast_rows(latest: dict) -> list[dict]:
    run_date = latest["today"]
    rows = []
    for r in latest["resorts"]:
        for d in r.get("days") or []:
            s, w = d["snow"], d["weather"]
            rows.append({
                "run_date": run_date, "resort": r["id"], "target": d["date"], "lead": d["lead"],
                "snow_base_cm": _fmt(w.get("snowfall_base_cm")), "snow_mid_cm": _fmt(w.get("snowfall_cm")),
                "snow_top_cm": _fmt(w.get("snowfall_top_cm")), "precip_mm": _fmt(w.get("precip_mm")),
                "snow_line_m": _fmt(w.get("snow_line_m"), 0), "t_mid": _fmt(w.get("t_mean_day_mid")),
                "sun_h": _fmt(w.get("sun_hours")), "gust_top": _fmt(w.get("gust_max_top"), 0),
                "state_mid": s.get("state", ""), "new_on_top_cm": _fmt(s.get("new_on_top_cm")),
                "hs": _fmt(s.get("hs"), 0), "hs_source": s.get("hs_source", ""),
                "score_freeride": _fmt(d["scores"].get("freeride")), "score_piste": _fmt(d["scores"].get("piste")),
                "confidence": _fmt(d.get("confidence"), 2),
            })
    return rows


def obs_rows(latest: dict, run_utc: str) -> list[dict]:
    rows = []
    for r in latest["resorts"]:
        for st in r.get("stations") or []:
            rows.append({
                "run_date": latest["today"], "run_utc": run_utc, "resort": r["id"], "station": st.get("name", ""),
                "elevation": _fmt(st.get("elevation"), 0), "obs_time": st.get("time") or "",
                "age_h": _fmt(st.get("age_h"), 2), "hs": _fmt(st.get("hs")), "hn24": _fmt(st.get("hn24")),
                "hn48": _fmt(st.get("hn48")), "hn72": _fmt(st.get("hn72")), "t_air": _fmt(st.get("t_air")),
                "t_surface": _fmt(st.get("t_surface")), "gust": _fmt(st.get("gust"), 0),
                "rejected": format_rejected(st.get("rejected")),
            })
    return rows


def write_archive(archive_dir: Path, latest: dict, now: datetime) -> dict:
    """Append today's rows if this run is the one that should write them. Returns what was written."""
    now_utc = now.astimezone(timezone.utc)
    run_date = latest["today"]
    run_utc = now_utc.strftime("%H:%M")
    written = {"forecast": 0, "obs": 0}
    # before 05:00 UTC, and late in the evening when the local date is already tomorrow, nothing is written
    if now_utc.hour < FORECAST_HOUR_UTC or now_utc.date().isoformat() != run_date:
        return written
    f_path = _month_file(archive_dir, "forecast", run_date)
    have_forecast = any(r["run_date"] == run_date for r in read_rows(archive_dir, "forecast", [run_date[:7]]))
    if not have_forecast:
        written["forecast"] = _append(f_path, FORECAST_FIELDS, forecast_rows(latest))
    o_path = _month_file(archive_dir, "obs", run_date)
    obs_today = [r for r in read_rows(archive_dir, "obs", [run_date[:7]]) if r["run_date"] == run_date]
    have_morning = bool(obs_today)
    have_midday = any(int(r["run_utc"][:2]) >= MIDDAY_HOUR_UTC for r in obs_today)
    if not have_morning or (now_utc.hour >= MIDDAY_HOUR_UTC and not have_midday):
        written["obs"] = _append(o_path, OBS_FIELDS, obs_rows(latest, run_utc))
    return written
