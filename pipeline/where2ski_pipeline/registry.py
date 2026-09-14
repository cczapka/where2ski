"""Resort registry loading."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Resort:
    id: str
    name: str
    region: str
    lat: float
    lon: float
    elevation: dict
    passes: list = field(default_factory=list)
    travel_min: int | None = None
    glacier: bool = False
    links: dict = field(default_factory=dict)
    micro_region: str | None = None
    aspect_rose: dict | None = None
    season: dict | None = None
    notes: str | None = None
    terrain: dict | None = None

    @property
    def base(self) -> float:
        return float(self.elevation["base"])

    @property
    def mid(self) -> float:
        return float(self.elevation["mid"])

    @property
    def top(self) -> float:
        return float(self.elevation["top"])

    def public(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "region": self.region,
            "lat": self.lat,
            "lon": self.lon,
            "elevation": self.elevation,
            "passes": list(self.passes),
            "travel_min": self.travel_min,
            "glacier": self.glacier,
            "links": dict(self.links),
            "micro_region": self.micro_region,
            "aspect_rose": self.aspect_rose,
            "season": self.season,
            "terrain": self.terrain,
        }


def load_terrain(path: Path | None) -> dict:
    if path is None or not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data.get("resorts", {}) if isinstance(data, dict) else {}


def load_resorts(path: Path, terrain_path: Path | None = None) -> list[Resort]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data["resorts"] if isinstance(data, dict) else data
    if terrain_path is None:
        candidate = Path(path).with_name("terrain.json")
        terrain_path = candidate if candidate.exists() else None
    terrain = load_terrain(terrain_path)
    resorts = []
    for item in items:
        resorts.append(
            Resort(
                id=item["id"],
                name=item["name"],
                region=item["region"],
                lat=float(item["lat"]),
                lon=float(item["lon"]),
                elevation=item["elevation"],
                passes=item.get("passes", []),
                travel_min=item.get("travel_min"),
                glacier=bool(item.get("glacier", False)),
                links=item.get("links", {}),
                micro_region=item.get("micro_region"),
                aspect_rose=item.get("aspect_rose"),
                season=item.get("season"),
                notes=item.get("notes"),
            )
        )
        t = terrain.get(item["id"])
        if t:
            resorts[-1].terrain = {k: v for k, v in t.items() if k != "aspect_rose"}
            if resorts[-1].aspect_rose is None and t.get("aspect_rose"):
                resorts[-1].aspect_rose = t["aspect_rose"]
    ids = [r.id for r in resorts]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate resort ids in registry")
    return resorts
