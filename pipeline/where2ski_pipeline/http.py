"""Small HTTP helper with on-disk caching and an offline fixture mode."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

USER_AGENT = "where2ski-pipeline/0.1 (+https://github.com/cczapka/where2ski)"


class Http:
    """GET with a key-based cache.

    In offline mode responses are read from ``offline_dir/<key>`` and no
    network access happens at all, which is what the tests use.
    """

    def __init__(self, cache_dir: Path | None = None, offline_dir: Path | None = None, timeout: float = 30.0):
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.offline_dir = Path(offline_dir) if offline_dir else None
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe(key: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", key)

    def get_text(self, url: str, key: str, ttl_s: float = 0, params: dict | None = None) -> str:
        if self.offline_dir is not None:
            path = self.offline_dir / self._safe(key)
            if not path.exists():
                raise FileNotFoundError(f"offline fixture missing: {path}")
            return path.read_text(encoding="utf-8")

        cache_path = self.cache_dir / self._safe(key) if self.cache_dir else None
        if cache_path and ttl_s > 0 and cache_path.exists():
            age = time.time() - cache_path.stat().st_mtime
            if age < ttl_s:
                return cache_path.read_text(encoding="utf-8")

        log.info("GET %s", url)
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        text = resp.text
        if cache_path and ttl_s > 0:
            cache_path.write_text(text, encoding="utf-8")
        return text

    def get_json(self, url: str, key: str, ttl_s: float = 0, params: dict | None = None):
        return json.loads(self.get_text(url, key, ttl_s=ttl_s, params=params))
