"""Build pipeline/data/terrain.json from OpenSkiData (OpenStreetMap-derived) runs.

For every resort in the registry the tool finds the OpenSkiMap ski area(s)
containing the resort point (or nearby ones), streams runs.geojson, keeps
downhill runs of those areas, and derives:

- an aspect rose: share of run length facing each of 8 compass sectors,
  using the downhill bearing of every run segment (from the 3-D coordinates),
- elevation statistics of the runs (5th/95th percentile, min, max),
- total run length and number of runs.

Usage (network required, meant for the terrain workflow):
    python -m tools.terrain --registry data/resorts.json --out data/terrain.json --cache cache
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import ijson
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from where2ski_pipeline.geo import haversine_km, point_in_geometry  # noqa: E402
from where2ski_pipeline.registry import load_resorts  # noqa: E402

log = logging.getLogger("terrain")

SKI_AREAS_URL = "https://tiles.openskimap.org/geojson/ski_areas.geojson"
RUNS_URL = "https://tiles.openskimap.org/geojson/runs.geojson"
ASPECTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def download(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        log.info("using cached %s (%.1f MB)", dest, dest.stat().st_size / 1e6)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    log.info("downloading %s", url)
    t0 = time.time()
    with requests.get(url, stream=True, timeout=600, headers={"User-Agent": "where2ski-terrain/0.1"}) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    log.info("downloaded %.1f MB in %.0f s", dest.stat().st_size / 1e6, time.time() - t0)
    return dest


def bearing_deg(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def sector(bearing: float) -> str:
    return ASPECTS[int(((bearing + 22.5) % 360) // 45)]


def geometry_centroid(geom: dict) -> tuple[float, float] | None:
    coords = geom.get("coordinates")
    gtype = geom.get("type")
    pts = []
    if gtype == "Point":
        return float(coords[1]), float(coords[0])
    if gtype == "Polygon":
        pts = coords[0]
    elif gtype == "MultiPolygon":
        pts = [p for poly in coords for p in poly[0]]
    elif gtype == "LineString":
        pts = coords
    if not pts:
        return None
    return sum(float(p[1]) for p in pts) / len(pts), sum(float(p[0]) for p in pts) / len(pts)


def match_ski_areas(resorts, ski_areas_path: Path, max_km: float) -> dict[str, list[dict]]:
    """resort id -> list of ski-area dicts {id, name}; point-in-polygon first, else nearest centroid."""
    matched: dict[str, list[dict]] = defaultdict(list)
    nearest: dict[str, tuple[float, dict]] = {}
    n = 0
    with ski_areas_path.open("rb") as f:
        for feature in ijson.items(f, "features.item", use_float=True):
            n += 1
            props = feature.get("properties") or {}
            if "downhill" not in (props.get("activities") or []):
                continue
            geom = feature.get("geometry") or {}
            info = {"id": props.get("id"), "name": props.get("name")}
            centroid = geometry_centroid(geom)
            for r in resorts:
                if geom.get("type") in ("Polygon", "MultiPolygon") and point_in_geometry(r.lon, r.lat, geom):
                    matched[r.id].append(info)
                elif centroid is not None:
                    d = haversine_km(r.lat, r.lon, centroid[0], centroid[1])
                    if d <= max_km and (r.id not in nearest or d < nearest[r.id][0]):
                        nearest[r.id] = (d, info)
    log.info("scanned %d ski areas", n)
    for r in resorts:
        override = (r.links or {}).get("openskimap_ids") if isinstance(r.links, dict) else None
        if override:
            matched[r.id] = [{"id": i, "name": None} for i in override]
        elif not matched[r.id] and r.id in nearest:
            matched[r.id] = [nearest[r.id][1]]
            log.info("%s: no containing ski area, using nearest '%s' (%.1f km)", r.id, nearest[r.id][1]["name"], nearest[r.id][0])
    return matched


class Accumulator:
    def __init__(self):
        self.sector_len = {a: 0.0 for a in ASPECTS}
        self.elevations: list[float] = []
        self.slopes: list[float] = []
        self.run_km = 0.0
        self.n_runs = 0
        self.names: set[str] = set()

    def add_run(self, coords: list, name: str | None):
        pts = [(float(c[1]), float(c[0]), float(c[2])) for c in coords if len(c) >= 3 and c[2] is not None and c[2] > -100]
        if len(pts) < 2:
            return
        self.n_runs += 1
        if name:
            self.names.add(name)
        for (lat0, lon0, z0), (lat1, lon1, z1) in zip(pts, pts[1:]):
            d = haversine_km(lat0, lon0, lat1, lon1) * 1000.0
            if d < 1.0:
                continue
            self.run_km += d / 1000.0
            self.elevations.extend((z0, z1))
            dz = z1 - z0
            if abs(dz) < 1.0 or abs(dz) / d < 0.03:
                continue  # flat: no meaningful aspect
            b = bearing_deg(lat0, lon0, lat1, lon1) if dz < 0 else bearing_deg(lat1, lon1, lat0, lon0)
            self.sector_len[sector(b)] += d
            self.slopes.append(abs(dz) / d)

    def result(self) -> dict | None:
        total = sum(self.sector_len.values())
        if self.n_runs == 0 or total <= 0:
            return None
        elev = sorted(self.elevations)

        def pct(p):
            return round(elev[min(len(elev) - 1, int(p * (len(elev) - 1)))])

        return {
            "aspect_rose": {a: round(v / total, 3) for a, v in self.sector_len.items()},
            "elev_min": round(elev[0]),
            "elev_p05": pct(0.05),
            "elev_p95": pct(0.95),
            "elev_max": round(elev[-1]),
            "run_km": round(self.run_km, 1),
            "n_runs": self.n_runs,
            "slope_median": round(sorted(self.slopes)[len(self.slopes) // 2], 3) if self.slopes else None,
        }


def build(registry: Path, out: Path, cache: Path, max_km: float, runs_url: str, ski_areas_url: str) -> dict:
    resorts = load_resorts(registry)
    ski_areas_path = download(ski_areas_url, cache / "ski_areas.geojson")
    matched = match_ski_areas(resorts, ski_areas_path, max_km)
    area_to_resorts: dict[str, list[str]] = defaultdict(list)
    for rid, areas in matched.items():
        for a in areas:
            if a.get("id"):
                area_to_resorts[a["id"]].append(rid)
    for r in resorts:
        log.info("%s -> %s", r.id, [a.get("name") or a.get("id") for a in matched.get(r.id, [])] or "NO MATCH (radius fallback)")

    runs_path = download(runs_url, cache / "runs.geojson")
    acc = {r.id: Accumulator() for r in resorts}
    unmatched = [r for r in resorts if not matched.get(r.id)]
    n = kept = 0
    t0 = time.time()
    with runs_path.open("rb") as f:
        for feature in ijson.items(f, "features.item", use_float=True):
            n += 1
            geom = feature.get("geometry") or {}
            if geom.get("type") != "LineString":
                continue
            props = feature.get("properties") or {}
            if "downhill" not in (props.get("uses") or []):
                continue
            if props.get("status") in ("abandoned", "disused"):
                continue
            targets: set[str] = set()
            for sa in props.get("skiAreas") or []:
                sid = ((sa.get("properties") or {}).get("id")) if isinstance(sa, dict) else None
                for rid in area_to_resorts.get(sid, []):
                    targets.add(rid)
            coords = geom.get("coordinates") or []
            if unmatched and coords:
                lat, lon = float(coords[0][1]), float(coords[0][0])
                for r in unmatched:
                    if haversine_km(r.lat, r.lon, lat, lon) <= max_km:
                        targets.add(r.id)
            for rid in targets:
                acc[rid].add_run(coords, props.get("name"))
                kept += 1
            if n % 100000 == 0:
                log.info("... %d runs scanned, %d kept, %.0f s", n, kept, time.time() - t0)
    log.info("scanned %d runs, kept %d", n, kept)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"runs": runs_url, "ski_areas": ski_areas_url, "license": "OpenSkiMap / OpenStreetMap contributors, ODbL"},
        "resorts": {},
    }
    for r in resorts:
        res = acc[r.id].result()
        if res is None:
            log.warning("%s: no downhill runs found", r.id)
            continue
        res["ski_areas"] = [a for a in matched.get(r.id, [])]
        result["resorts"][r.id] = res
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def print_summary(result: dict) -> None:
    print(f"{'resort':24} {'runs':>4} {'km':>6} {'p05':>5} {'p95':>5}  rose (N NE E SE S SW W NW)")
    for rid, t in result["resorts"].items():
        rose = " ".join(f"{int(round(t['aspect_rose'][a] * 100)):2d}" for a in ASPECTS)
        print(f"{rid:24} {t['n_runs']:4d} {t['run_km']:6.1f} {t['elev_p05']:5d} {t['elev_p95']:5d}  {rose}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default="data/resorts.json")
    ap.add_argument("--out", default="data/terrain.json")
    ap.add_argument("--cache", default="cache/terrain")
    ap.add_argument("--max-km", type=float, default=6.0)
    ap.add_argument("--runs-url", default=RUNS_URL)
    ap.add_argument("--ski-areas-url", default=SKI_AREAS_URL)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    result = build(Path(args.registry), Path(args.out), Path(args.cache), args.max_km, args.runs_url, args.ski_areas_url)
    print_summary(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
