"""Constants: source URLs, model parameters and scoring weights."""

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
STATIONS_URL = "https://static.avalanche.report/eaws_weather_stations/linea.geojson"
MICRO_REGIONS_URL = "https://regions.avalanches.org/micro-regions/{region}_micro-regions.geojson.json"
HOLIDAYS_BASE = "https://openholidaysapi.org"

# Bulletin sources per warning region, tried in order. "caaml" files are
# CAAML v6 JSON (EUREGIO: Tyrol, South Tyrol, Trentino). "ratings" is the EAWS
# aggregation file for all of Europe ({"maxDangerRatings": {"DE-BY-10": 2, "DE-BY-10:pm": 3, ...}}).
# "dated" entries contain the date in the URL and are valid for that date only;
# undated ones are validated against their own validTime after download.
BULLETIN_SOURCES = {
    "AT-07": [
        {"url": "https://static.avalanche.report/bulletins/{date}/{date}_EUREGIO_de_CAAMLv6.json", "kind": "caaml", "dated": True},
        {"url": "https://static.avalanche.report/bulletins/latest/EUREGIO_de_CAAMLv6.json", "kind": "caaml", "dated": False},
    ],
    "DE-BY": [
        {"url": "https://static.avalanche.report/eaws_bulletins/{date}/{date}.ratings.json", "kind": "ratings", "dated": True},
    ],
    "AT-05": [
        {"url": "https://static.avalanche.report/eaws_bulletins/{date}/{date}.ratings.json", "kind": "ratings", "dated": True},
    ],
}

# Default season ("MM-DD" open/close) when the registry gives none.
DEFAULT_SEASON = ("12-01", "04-15")
GLACIER_SEASON = ("10-01", "05-31")

# OpenHolidays subdivision codes used for the crowd factor.
HOLIDAY_REGIONS = [("DE", "DE-BY"), ("AT", "AT-7"), ("AT", "AT-5")]

HOME = {"name": "München", "lat": 48.137, "lon": 11.575}
TIMEZONE = "Europe/Berlin"
PAST_DAYS = 10
FORECAST_DAYS = 10

HOURLY_VARS = [
    "temperature_2m",
    "precipitation",
    "rain",
    "snowfall",
    "snow_depth",
    "freezing_level_height",
    "sunshine_duration",
    "cloud_cover_low",
    "cloud_cover",
    "visibility",
    "wind_speed_10m",
    "wind_gusts_10m",
    "weather_code",
]

STATION_MAX_KM = 10.0
STATION_MAX_DZ = 400.0
STATION_MAX_COUNT = 3

# Scoring weights (see docs/CONCEPT.md §6). Values are relative.
WEIGHTS = {
    "freeride": {
        "fresh_snow": 25,
        "snow_quality": 25,
        "avalanche": 20,
        "sun_vis": 10,
        "wind": 5,
        "temperature": 5,
        "base": 0,
        "travel": 5,
        "crowd": 5,
        "roads": 5,
    },
    "piste": {
        "fresh_snow": 15,
        "snow_quality": 15,
        "avalanche": 0,
        "sun_vis": 30,
        "wind": 10,
        "temperature": 10,
        "base": 10,
        "travel": 5,
        "crowd": 5,
        "roads": 5,
    },
}

# Base depth thresholds in cm.
BASE_MIN_PISTE = 30
BASE_MIN_FREERIDE = 60

LEAD_CONFIDENCE = [1.0, 0.95, 0.85, 0.7, 0.6, 0.5, 0.4, 0.35, 0.3, 0.25]

ATTRIBUTION = [
    "Weather data by Open-Meteo.com (CC BY 4.0)",
    "Station data: EAWS partner services via lawinen.report / avalanche.report",
    "Avalanche bulletins: EUREGIO avalanche.report and EAWS",
    "Warning regions: eaws-regions (regions.avalanches.org)",
    "Holidays: OpenHolidays API",
]
