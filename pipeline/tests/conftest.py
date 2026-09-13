"""Shared helpers: synthetic Open-Meteo responses and small fixtures."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pytest

from where2ski_pipeline.sources.openmeteo import HourlySeries

TODAY = date(2026, 1, 15)


def make_series(today: date = TODAY, past_days: int = 10, forecast_days: int = 10, elevation: float = 1500,
                temp=lambda t: -5.0, snowfall=lambda t: 0.0, rain=lambda t: 0.0, sun=lambda t: 0.0,
                gust=lambda t: 20.0, low_cloud=lambda t: 20.0, snow_depth=lambda t: 1.0) -> HourlySeries:
    start = datetime.combine(today - timedelta(days=past_days), datetime.min.time())
    n = (past_days + forecast_days) * 24
    times = [start + timedelta(hours=i) for i in range(n)]
    values = {
        "temperature_2m": [temp(t) for t in times],
        "precipitation": [snowfall(t) / 7.0 + rain(t) for t in times],
        "rain": [rain(t) for t in times],
        "snowfall": [snowfall(t) for t in times],
        "snow_depth": [snow_depth(t) for t in times],
        "freezing_level_height": [1500.0 + 100 * temp(t) for t in times],
        "sunshine_duration": [sun(t) for t in times],
        "cloud_cover_low": [low_cloud(t) for t in times],
        "cloud_cover": [low_cloud(t) for t in times],
        "visibility": [20000.0 for _ in times],
        "wind_speed_10m": [gust(t) / 2 for t in times],
        "wind_gusts_10m": [gust(t) for t in times],
        "weather_code": [0 for _ in times],
    }
    return HourlySeries(times=times, values=values, elevation=elevation)


def series_to_openmeteo_json(series_by_band: dict) -> list:
    out = []
    for band in ("base", "mid", "top"):
        s = series_by_band[band]
        out.append({
            "latitude": 47.2, "longitude": 11.0, "elevation": s.elevation,
            "hourly": {"time": [t.strftime("%Y-%m-%dT%H:%M") for t in s.times], **s.values},
        })
    return out


def daytime_sun(t: datetime, hours: float = 7.0) -> float:
    """seconds of sunshine per hour between 9 and 9+hours."""
    return 3600.0 if 9 <= t.hour < 9 + hours else 0.0


STATIONS_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [11.02, 47.21, 2050]},
         "properties": {"name": "Kühtai Test", "operator": "LWD Tirol",
                        "measurements": {"HS": 112, "HSD24": 18, "HSD48": 24, "HSD72": 30, "LT": -6.5, "OFT": -9.0, "WG": 28},
                        "date": "2026-01-15T07:00:00+01:00"}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [11.05, 47.23]},
         "properties": {"name": "Far Too High", "elevation": 2950, "HS": "60", "LT": "-12"}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [12.5, 47.5]},
         "properties": {"name": "Other Valley", "elevation": 1500, "HS": 40, "LT": -2}},
    ],
}

CAAML = {
    "bulletins": [
        {
            "bulletinID": "x",
            "validTime": {"startTime": "2026-01-15T00:00:00Z", "endTime": "2026-01-16T00:00:00Z"},
            "regions": [{"regionID": "AT-07-14", "name": "Test region"}],
            "dangerRatings": [
                {"mainValue": "considerable", "elevation": {"lowerBound": "2200"}, "validTimePeriod": "all_day"},
                {"mainValue": "moderate", "elevation": {"upperBound": "2200"}, "validTimePeriod": "all_day"},
            ],
            "avalancheProblems": [
                {"problemType": "wind_slab", "aspects": ["N", "NE", "E"], "elevation": {"lowerBound": "2200"},
                 "validTimePeriod": "all_day"}
            ],
            "tendency": [{"tendencyType": "steady"}],
        }
    ]
}

MICRO_REGIONS = {
    "type": "FeatureCollection",
    "features": [
        {"type": "Feature", "properties": {"id": "AT-07-14"},
         "geometry": {"type": "Polygon", "coordinates": [[[10.9, 47.1], [11.2, 47.1], [11.2, 47.3], [10.9, 47.3], [10.9, 47.1]]]}}
    ],
}

HOLIDAYS_SCHOOL = [{"id": "1", "startDate": "2026-02-16", "endDate": "2026-02-20", "type": "School"}]
HOLIDAYS_PUBLIC = [{"id": "2", "startDate": "2026-01-06", "endDate": "2026-01-06", "type": "Public"}]


@pytest.fixture
def registry_path(tmp_path):
    reg = {"resorts": [
        {"id": "kuehtai", "name": "Kühtai", "region": "AT-07", "lat": 47.213, "lon": 11.011,
         "elevation": {"base": 2020, "mid": 2300, "top": 2520}, "passes": ["snowcard_tirol"], "travel_min": 120},
        {"id": "sudelfeld", "name": "Sudelfeld", "region": "DE-BY", "lat": 47.679, "lon": 12.04,
         "elevation": {"base": 800, "mid": 1300, "top": 1563}, "passes": ["alpen_plus"], "travel_min": 65},
    ]}
    p = tmp_path / "resorts.json"
    p.write_text(json.dumps(reg), encoding="utf-8")
    return p


@pytest.fixture
def offline_dir(tmp_path):
    d = tmp_path / "fixtures"
    d.mkdir()
    powder = {
        "base": make_series(elevation=2020, temp=lambda t: -4.0,
                            snowfall=lambda t: 2.0 if (TODAY - timedelta(days=1)) == t.date() and 6 <= t.hour < 18 else 0.0),
        "mid": make_series(elevation=2300, temp=lambda t: -7.0, sun=lambda t: daytime_sun(t, 6),
                           snowfall=lambda t: 2.5 if (TODAY - timedelta(days=1)) == t.date() and 6 <= t.hour < 18 else 0.0),
        "top": make_series(elevation=2520, temp=lambda t: -10.0, gust=lambda t: 25.0),
    }
    warm = {
        "base": make_series(elevation=800, temp=lambda t: 6.0, snow_depth=lambda t: 0.1),
        "mid": make_series(elevation=1300, temp=lambda t: 4.0 if 9 <= t.hour < 18 else 1.0, snow_depth=lambda t: 0.25,
                           sun=lambda t: daytime_sun(t, 5)),
        "top": make_series(elevation=1563, temp=lambda t: 2.0, gust=lambda t: 45.0),
    }
    (d / "openmeteo_kuehtai.json").write_text(json.dumps(series_to_openmeteo_json(powder)))
    (d / "openmeteo_sudelfeld.json").write_text(json.dumps(series_to_openmeteo_json(warm)))
    (d / "stations.geojson").write_text(json.dumps(STATIONS_GEOJSON))
    (d / "bulletin_AT-07.json").write_text(json.dumps(CAAML))
    (d / "micro_regions_AT-07.json").write_text(json.dumps(MICRO_REGIONS))
    for sub in ("DE-BY", "AT-7", "AT-5"):
        (d / f"holidays_{sub}_school.json").write_text(json.dumps(HOLIDAYS_SCHOOL))
        (d / f"holidays_{sub}_public.json").write_text(json.dumps(HOLIDAYS_PUBLIC))
    return d
