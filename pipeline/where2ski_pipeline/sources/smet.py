"""Station time series in SMET format (MeteoIO), as linked from the EAWS station feed."""

from __future__ import annotations

import gzip
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .. import config
from ..http import Http

log = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo(config.TIMEZONE)

# raw SMET units (SI) -> model units
CONVERT = {
    "TA": lambda v: v - 273.15 if v > 150 else v,
    "TSS": lambda v: v - 273.15 if v > 150 else v,
    "HS": lambda v: v * 100.0 if v < 20 else v,  # metres -> cm (values >= 20 are assumed to be cm already)
}


@dataclass
class StationHistory:
    station: str
    times: list[datetime] = field(default_factory=list)  # local wall time, naive (like the forecast series)
    values: dict[str, list] = field(default_factory=dict)
    hourly: dict[datetime, dict] = field(default_factory=dict)

    @property
    def start(self) -> datetime | None:
        return self.times[0] if self.times else None

    @property
    def end(self) -> datetime | None:
        return self.times[-1] if self.times else None

    def build_hourly(self) -> None:
        """Aggregate the 10-minute rows to hourly means for TA, TSS, HS."""
        buckets: dict[datetime, dict[str, list]] = {}
        for i, t in enumerate(self.times):
            hour = t.replace(minute=0, second=0, microsecond=0)
            b = buckets.setdefault(hour, {"ta": [], "tss": [], "hs": []})
            for key, col in (("ta", "TA"), ("tss", "TSS"), ("hs", "HS")):
                vals = self.values.get(col)
                if vals is not None and vals[i] is not None:
                    b[key].append(vals[i])
        self.hourly = {
            hour: {k: (sum(v) / len(v) if v else None) for k, v in b.items()} for hour, b in buckets.items()
        }


def parse_smet(text: str, station: str = "") -> StationHistory:
    fields: list[str] = []
    nodata = "-777"
    tz_offset = 0.0
    in_data = False
    hist = StationHistory(station=station)
    cols: dict[str, list] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[DATA]"):
            in_data = True
            continue
        if not in_data:
            if "=" in line:
                key, _, val = line.partition("=")
                key, val = key.strip().lower(), val.strip()
                if key == "fields":
                    fields = val.split()
                    cols = {f: [] for f in fields if f != "timestamp"}
                elif key == "nodata":
                    nodata = val
                elif key == "tz":
                    try:
                        tz_offset = float(val)
                    except ValueError:
                        tz_offset = 0.0
                elif key in ("station_id", "station_name") and not hist.station:
                    hist.station = val
            continue
        cells = line.split()
        if not fields or len(cells) != len(fields):
            continue
        stamp = cells[0]
        try:
            if stamp.endswith("Z"):
                t = datetime.fromisoformat(stamp[:-1]).replace(tzinfo=timezone.utc)
            else:
                t = datetime.fromisoformat(stamp)
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone(timedelta(hours=tz_offset)))
        except ValueError:
            continue
        local = t.astimezone(LOCAL_TZ).replace(tzinfo=None)
        hist.times.append(local)
        for name, cell in zip(fields[1:], cells[1:]):
            if cell == nodata or cell in ("-999", "-999.0", "nan", "NaN"):
                cols[name].append(None)
                continue
            try:
                v = float(cell)
            except ValueError:
                cols[name].append(None)
                continue
            conv = CONVERT.get(name)
            cols[name].append(conv(v) if conv else v)
    hist.values = cols
    hist.build_hourly()
    return hist


def parse_geosphere(data: dict, station: str = "") -> StationHistory:
    """GeoSphere Austria dataset API GeoJSON time series (TAWES): TL in °C, SCHNEE in cm, no surface temperature."""
    hist = StationHistory(station=station)
    stamps = data.get("timestamps") or []
    features = data.get("features") or []
    if not stamps or not features:
        return hist
    params = (features[0].get("properties") or {}).get("parameters") or {}
    if not hist.station:
        hist.station = str((features[0].get("properties") or {}).get("station") or "")

    def column(*names):
        for n in names:
            block = params.get(n)
            if isinstance(block, dict) and isinstance(block.get("data"), list):
                return block["data"]
        return None

    ta = column("TL", "TA")
    hs = column("SCHNEE", "SH", "HS")
    for i, stamp in enumerate(stamps):
        try:
            t = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        except ValueError:
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        hist.times.append(t.astimezone(LOCAL_TZ).replace(tzinfo=None))
        for name, col in (("TA", ta), ("HS", hs)):
            if col is not None:
                v = col[i] if i < len(col) else None
                hist.values.setdefault(name, []).append(float(v) if isinstance(v, (int, float)) else None)
    hist.build_hourly()
    return hist


def parse_history(raw: bytes, station: str = "") -> StationHistory | None:
    """Detect gzip, SMET or GeoSphere JSON and parse accordingly."""
    if raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.decompress(raw)
        except OSError as exc:
            log.warning("station history: gzip failed: %s", exc)
            return None
    text = raw.decode("utf-8", errors="replace")
    head = text.lstrip()[:40]
    if head.startswith("SMET"):
        return parse_smet(text, station=station)
    if head.startswith("{"):
        try:
            data = json.loads(text)
        except ValueError:
            return None
        if isinstance(data, dict) and "timestamps" in data:
            return parse_geosphere(data, station=station)
    log.warning("station history: unknown format (starts with %r)", head)
    return None


def fetch_history(http: Http, station, ttl_s: float = 3600) -> StationHistory | None:
    urls = getattr(station, "data_urls", None) or []
    for url in urls[:1]:
        key = "history_" + "".join(ch if ch.isalnum() else "_" for ch in url)[-80:]
        try:
            raw = http.get_bytes(url, key=key, ttl_s=ttl_s)
        except Exception as exc:  # noqa: BLE001
            log.warning("station history %s failed: %s", url, exc)
            return None
        hist = parse_history(raw, station=getattr(station, "name", ""))
        if hist is None or not hist.times:
            return None
        return hist
    return None
