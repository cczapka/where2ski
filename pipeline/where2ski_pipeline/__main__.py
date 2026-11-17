"""CLI: python -m where2ski_pipeline run --out out"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path

from .run import run


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="where2ski_pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="fetch sources, score resorts, write JSON")
    p.add_argument("--registry", default="data/resorts.json")
    p.add_argument("--out", default="out")
    p.add_argument("--cache", default="cache")
    p.add_argument("--offline", default=None, help="directory with fixture responses instead of network access")
    p.add_argument("--record", default=None,
                   help="write every raw response into this directory; replay it later with --offline")
    p.add_argument("--archive", default=None,
                   help="archive directory (checkout of the data branch): read yesterday's readings, append today's rows")
    p.add_argument("--today", default=None, help="override today's date (YYYY-MM-DD)")
    p.add_argument("--now", default=None, help="override the run time (ISO 8601 with offset)")
    p.add_argument("--only", nargs="*", default=None, help="restrict to these resort ids")
    p.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    latest = run(
        registry=Path(args.registry),
        out_dir=Path(args.out),
        cache_dir=None if args.offline else Path(args.cache),
        offline_dir=Path(args.offline) if args.offline else None,
        today=date.fromisoformat(args.today) if args.today else None,
        only=args.only,
        record_dir=Path(args.record) if args.record else None,
        now=datetime.fromisoformat(args.now) if args.now else None,
        archive_dir=Path(args.archive) if args.archive else None,
    )
    for warning in latest["status"].get("warnings", []):
        print(f"::warning::{warning}")
    if latest["status"].get("archive"):
        print("archive rows written:", latest["status"]["archive"])
    errors = [r["id"] for r in latest["resorts"] if r.get("error")]
    print(f"resorts: {len(latest['resorts'])}, errors: {len(errors)} {errors}")
    print("sources:", latest["status"]["sources"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
