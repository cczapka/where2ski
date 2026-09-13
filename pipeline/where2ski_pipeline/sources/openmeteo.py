"""Open-Meteo forecast access, one request per resort at three elevations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .. import config
from ..http import Http

BANDS = ("base", "mid", "top")


@dataclass
class HourlySeries:
    times: list[datetime]
    values: dict[str, list] = field(default_factory=dict)
    elevation: float | None = None

    def get(self, var: str) -> list:
        return self.values.get(var) or [None] * len(self.times)

    def indices(self, start: datetime, end: datetime) -> range:
        """Indices with start <= t < end (times are sorted)."""
        lo = 0
        while lo < len(self.times) and self.times[lo] < start:
            lo += 1
        hi = lo
        while hi < len(self.times) and self.times[hi] < end:
            hi += 1
        return range(lo, hi)

    def slice(self, var: str, start: datetime, end: datetime) -> list:
        vals = self.get(var)
        return [vals[i] for i in self.indices(start, end)]


def parse_hourly(block: dict) -> HourlySeries:
    hourly = block.get("hourly") or {}
    times = [datetime.fromisoformat(t) for t in hourly.get("time", [])]
    values = {k: v for k, v in hourly.items() if k != "time"}
    return HourlySeries(times=times, values=values, elevation=block.get("elevation"))


def fetch_resort_forecast(http: Http, resort) -> dict[str, HourlySeries]:
    elevations = [resort.base, resort.mid, resort.top]
    params = {
        "latitude": ",".join(f"{resort.lat:.4f}" for _ in BANDS),
        "longitude": ",".join(f"{resort.lon:.4f}" for _ in BANDS),
        "elevation": ",".join(f"{e:.0f}" for e in elevations),
        "hourly": ",".join(config.HOURLY_VARS),
        "past_days": config.PAST_DAYS,
        "forecast_days": config.FORECAST_DAYS,
        "timezone": config.TIMEZONE,
        "models": "best_match",
    }
    data = http.get_json(config.OPEN_METEO_URL, key=f"openmeteo_{resort.id}.json", params=params)
    blocks = data if isinstance(data, list) else [data]
    if len(blocks) != len(BANDS):
        # A single block means the API collapsed the request; reuse it for every band.
        blocks = [blocks[0]] * len(BANDS)
    return {band: parse_hourly(block) for band, block in zip(BANDS, blocks)}
