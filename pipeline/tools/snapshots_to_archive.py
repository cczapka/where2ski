"""Convert the daily JSON snapshots (Sep-Nov 2026) into day-0 archive rows.

The snapshots hold the station readings of one run per day and the day-0
forecast. Readings are aged against the snapshot's own run time and pass the
same quality control as live runs (yesterday's value from the previous
snapshot, precipitation from that day's forecast). Lead days 1-9 were never
stored, so only lead 0 is written.

    python -m tools.snapshots_to_archive data/snapshots ARCHIVE_DIR
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from where2ski_pipeline.archive import FORECAST_FIELDS, OBS_FIELDS, _append, forecast_rows, obs_rows
from where2ski_pipeline.sources.stations import MappedStation, Station, mark_age, quality_control

STATION_KEYS = ("name", "lat", "lon", "elevation", "hs", "hn24", "hn48", "hn72", "t_air", "t_surface", "gust",
                "time", "operator", "micro_region")


def convert(snap_dir: Path, archive_dir: Path) -> dict:
    files = sorted(Path(snap_dir).glob("*.json"))
    counts = {"days": 0, "forecast": 0, "obs": 0, "rejected": 0}
    previous: dict[str, dict[str, float]] = {}
    archive_dir.mkdir(parents=True, exist_ok=True)
    for f in files:
        snap = json.loads(f.read_text(encoding="utf-8"))
        now = datetime.fromisoformat(snap["generated_at"])
        latest = {"today": snap["date"], "resorts": []}
        current: dict[str, dict[str, float]] = {}
        for rid, item in snap["resorts"].items():
            day0 = item.get("today")
            stations = [Station(**{k: s.get(k) for k in STATION_KEYS}) for s in item.get("stations") or []]
            mark_age(stations, now)
            precip = (day0 or {}).get("weather", {}).get("precip_mm")
            checked = quality_control([MappedStation(s, 0.0, 1.0) for s in stations],
                                      yesterday_hs=previous.get(rid), precip_24h_mm=precip)
            out_stations = [m.station.public() for m in checked]
            counts["rejected"] += sum(1 for s in out_stations if s["rejected"] and not s["stale"])
            current[rid] = {s["name"]: s["hs"] for s in out_stations if s["hs"] is not None}
            latest["resorts"].append({"id": rid, "days": [day0] if day0 else [], "stations": out_stations})
        previous = current
        month = snap["date"][:7]
        counts["forecast"] += _append(archive_dir / f"forecast-{month}.csv", FORECAST_FIELDS, forecast_rows(latest))
        counts["obs"] += _append(archive_dir / f"obs-{month}.csv", OBS_FIELDS,
                                 obs_rows(latest, now.strftime("%H:%M")))
        counts["days"] += 1
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("snapshots", type=Path)
    ap.add_argument("archive", type=Path)
    args = ap.parse_args(argv)
    if any(args.archive.glob("*.csv")):
        print(f"{args.archive} already holds CSV files; convert into an empty directory", file=sys.stderr)
        return 1
    print(convert(args.snapshots, args.archive))
    return 0


if __name__ == "__main__":
    sys.exit(main())
