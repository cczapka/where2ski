"""School and public holidays from the OpenHolidays API, used for a crowd factor."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from .. import config
from ..http import Http

log = logging.getLogger(__name__)


def _dates(items) -> set[date]:
    out: set[date] = set()
    for item in items or []:
        try:
            start = date.fromisoformat(item["startDate"][:10])
            end = date.fromisoformat(item.get("endDate", item["startDate"])[:10])
        except (KeyError, ValueError):
            continue
        d = start
        while d <= end:
            out.add(d)
            d += timedelta(days=1)
    return out


def fetch_holidays(http: Http, start: date, end: date) -> tuple[dict[str, set[date]], dict]:
    """Return {'school': dates, 'public': dates} over all configured regions."""
    result = {"school": set(), "public": set()}
    status = {"ok": 0, "failed": []}
    for country, subdivision in config.HOLIDAY_REGIONS:
        for kind, endpoint in (("school", "SchoolHolidays"), ("public", "PublicHolidays")):
            params = {
                "countryIsoCode": country,
                "subdivisionCode": subdivision,
                "validFrom": start.isoformat(),
                "validTo": end.isoformat(),
                "languageIsoCode": "DE",
            }
            key = f"holidays_{subdivision}_{kind}.json"
            try:
                data = http.get_json(f"{config.HOLIDAYS_BASE}/{endpoint}", key=key, ttl_s=7 * 86400, params=params)
            except Exception as exc:  # noqa: BLE001
                status["failed"].append(f"{subdivision}/{kind}: {exc}")
                log.warning("holidays %s %s failed: %s", subdivision, kind, exc)
                continue
            result[kind] |= _dates(data)
            status["ok"] += 1
    return result, status


def crowd_factor(day: date, holidays: dict[str, set[date]]) -> float:
    weekend = day.weekday() >= 5
    school = day in holidays.get("school", set())
    public = day in holidays.get("public", set())
    if weekend and (school or public):
        return 0.5
    if weekend:
        return 0.7
    if public:
        return 0.6
    if school:
        return 0.8
    return 1.0
