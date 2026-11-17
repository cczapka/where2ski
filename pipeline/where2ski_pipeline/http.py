"""Small HTTP helper with on-disk caching, an offline fixture mode and a recorder.

Recording (``record_dir``) writes every response under its cache key, and every
failed request as ``<key>.error`` holding the error text. Replaying that
directory with ``offline_dir`` reproduces the run without network access, so
any real day can serve as a regression fixture.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

USER_AGENT = "where2ski-pipeline/0.1 (+https://github.com/cczapka/where2ski)"


class RecordedError(RuntimeError):
    """A request that failed while recording; replayed with the same message."""


class Http:
    def __init__(self, cache_dir: Path | None = None, offline_dir: Path | None = None, timeout: float = 30.0,
                 record_dir: Path | None = None):
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.offline_dir = Path(offline_dir) if offline_dir else None
        self.record_dir = Path(record_dir) if record_dir else None
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.last_modified: dict[str, str] = {}  # cache key -> Last-Modified header of the live response
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        if self.record_dir:
            self.record_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe(key: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", key)

    def _record(self, name: str, data: bytes) -> None:
        if self.record_dir is not None:
            (self.record_dir / name).write_bytes(data)

    def _get(self, url: str, key: str, ttl_s: float, params: dict | None, binary: bool) -> bytes:
        name = self._safe(key)
        if self.offline_dir is not None:
            path = self.offline_dir / name
            if path.exists():
                data = path.read_bytes()
                self._record(name, data)
                return data
            failed = self.offline_dir / (name + ".error")
            if failed.exists():
                self._record(name + ".error", failed.read_bytes())
                text = failed.read_text(encoding="utf-8")
                raise (FileNotFoundError if text.startswith("offline fixture missing") else RecordedError)(text)
            message = f"offline fixture missing: {name}"
            self._record(name + ".error", message.encode("utf-8"))
            raise FileNotFoundError(message)

        cache_path = self.cache_dir / (name + (".bin" if binary else "")) if self.cache_dir else None
        if cache_path and ttl_s > 0 and cache_path.exists():
            if time.time() - cache_path.stat().st_mtime < ttl_s:
                data = cache_path.read_bytes()
                self._record(name, data)
                return data

        log.info("GET %s", url)
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
        except Exception as exc:
            self._record(name + ".error", str(exc).encode("utf-8"))
            raise
        stamp = resp.headers.get("Last-Modified")
        if stamp:
            self.last_modified[key] = stamp
        data = resp.content if binary else resp.text.encode("utf-8")
        if cache_path and ttl_s > 0:
            cache_path.write_bytes(data)
        self._record(name, data)
        return data

    def get_text(self, url: str, key: str, ttl_s: float = 0, params: dict | None = None) -> str:
        return self._get(url, key, ttl_s, params, binary=False).decode("utf-8")

    def get_bytes(self, url: str, key: str, ttl_s: float = 0, params: dict | None = None) -> bytes:
        """Raw body, needed for gzip files served without Content-Encoding."""
        return self._get(url, key, ttl_s, params, binary=True)

    def get_json(self, url: str, key: str, ttl_s: float = 0, params: dict | None = None):
        return json.loads(self.get_text(url, key, ttl_s=ttl_s, params=params))
