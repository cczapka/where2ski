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
    notes: str | None = None

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
        }


def load_resorts(path: Path) -> list[Resort]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data["resorts"] if isinstance(data, dict) else data
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
                notes=item.get("notes"),
            )
        )
    ids = [r.id for r in resorts]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate resort ids in registry")
    return resorts
