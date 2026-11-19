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
    "relative_humidity_2m",
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

# Snowfall per band: "api" uses the weather service's value, "derived" the
# wet-bulb phase and Hedstrom-Pomeroy density of model/precip.py. Chosen by
# experiment 7.1 (docs/PLAN.md); both are always computed for comparison.
# Backtest 15 Oct-17 Nov 2026, mid band >= 1700 m, 48 snow days: the service's
# value found 14, derived 26 (ETS 0.21 -> 0.25), at a false-alarm ratio of 0.61.
SNOWFALL_SOURCE = "derived"
# Query point per band: "registry" (resort point at the registry elevations)
# or "terrain" (centroid of that third of the runs, tools/terrain.py).
# Terrain points did not help in the same backtest (13 and 22 hits), so registry.
QUERY_POINTS = "registry"

STATION_MAX_KM = 10.0
STATION_MAX_DZ = 250.0  # per band (docs/PLAN.md 7.4); 400 m kept 3 more resorts but less representative stations
STATION_MAX_COUNT = 3
# Readings older than this are not used. Normal age is 0.3-1 h for every
# operator (snapshots Sep-Nov 2026); runs are 3 h apart.
STATION_MAX_AGE_H = 3.0
STALE_WARNING_SHARE = 0.5  # warn when more than half of all stations with readings are stale

# Station quality control (docs/PLAN.md 5.2). Starting values from the review.
QC_HS_MAX_CM = 600.0          # snow height outside 0..600 cm is dropped
QC_HN24_MAX_CM = 150.0        # a 24 h change above this is dropped outright
QC_HN24_CONFIRM_CM = 60.0     # above this, another mapped station must confirm ...
QC_HN24_SUPPORT_CM = 30.0     # ... with at least this much
QC_HS_JUMP_CM = 60.0          # day-to-day jump in snow height, unless the forecast had ...
QC_JUMP_PRECIP_MM = 20.0      # ... at least this much precipitation in 24 h
QC_BARE_HS_CM = 60.0          # below this, with air above QC_BARE_T_AIR and no modelled snow,
QC_BARE_T_AIR = 8.0           # the sensor reads vegetation: set to 0 (Saalbach, October 2026)
GLACIER_STATION_MAX_DZ = 250.0  # a glacier depth measurement must lie this close to the top band

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

# Projected base depth: settled new snow minus melt. 1 cm per positive degree-day
# at the band is a starting value, to be calibrated against the stations.
SETTLING_FACTOR = 0.7
DEGREE_DAY_CM = 1.0

# Base depth thresholds in cm.
BASE_MIN_PISTE = 30
BASE_MIN_FREERIDE = 60          # mid band below 2000 m: meadows and forest floor
BASE_MIN_FREERIDE_ALPINE = 80   # mid band at or above 2000 m: rock and scree
BASE_MIN_FREERIDE_GLACIER = 120  # measured near the top band; crevasses (decision of 16 Nov 2026)
ALPINE_MID_M = 2000
GLACIER_THIN_PISTE_FACTOR = 0.8  # piste quality on a glacier with less than BASE_MIN_PISTE natural snow

# Avalanche factor when no rating applies (docs/PLAN.md 5.4)
AVALANCHE_OUT_OF_SEASON = 0.4
AVALANCHE_FETCH_FAILED = 0.5
BEYOND_BULLETIN_CONFIDENCE = 0.8

LIMITED_OPENING_PISTE = 0.6  # piste score multiplier between season open and limited_until

LEAD_CONFIDENCE = [1.0, 0.95, 0.85, 0.7, 0.6, 0.5, 0.4, 0.35, 0.3, 0.25]

ATTRIBUTION = [
    "Weather data by Open-Meteo.com (CC BY 4.0)",
    "Station data: EAWS partner services via lawinen.report / avalanche.report",
    "Avalanche bulletins: EUREGIO avalanche.report and EAWS",
    "Warning regions: eaws-regions (regions.avalanches.org)",
    "Holidays: OpenHolidays API",
]
