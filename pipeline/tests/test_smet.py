from datetime import datetime

import gzip
import json

from where2ski_pipeline.sources.smet import parse_geosphere, parse_history, parse_smet

SMET = """SMET 1.1 ASCII
[HEADER]
station_id = AXLIZ1
station_name = Speicherteich Axamer Lizum
latitude = 47.18
longitude = 11.29
altitude = 2103.0
nodata = -777
fields = timestamp ISWR HS RH TA PSUM TD TSS VW VW_MAX DW
#units = ISO8601 W/m² m 1 K mm K K m/s m/s °
[DATA]
2026-01-15T05:00:00Z 0 1.553 0.995 262.25 0 262.18 261.5 0.41 0.88 234
2026-01-15T05:10:00Z 0 1.554 0.995 262.25 0 262.18 -777 1.26 1.87 217
2026-01-15T05:20:00Z 0 1.553 0.995 262.35 0 262.28 261.3 1.1 2.87 221
2026-01-15T11:00:00Z 600 1.540 0.7 274.15 0 262.0 273.05 1.0 2.0 200
2026-01-15T11:30:00Z 610 1.538 0.7 274.65 0 262.0 273.15 1.0 2.0 200
"""


def test_parse_smet_units_and_hourly():
    h = parse_smet(SMET)
    assert h.station == "AXLIZ1"
    assert len(h.times) == 5
    # UTC 05:00 -> 06:00 local (CET)
    assert h.times[0] == datetime(2026, 1, 15, 6, 0)
    assert abs(h.values["HS"][0] - 155.3) < 1e-6
    assert abs(h.values["TA"][0] - (-10.9)) < 1e-6
    assert h.values["TSS"][1] is None  # nodata
    six = h.hourly[datetime(2026, 1, 15, 6, 0)]
    assert abs(six["ta"] - (-10.866667)) < 1e-3
    assert abs(six["tss"] - (-11.75)) < 1e-6  # mean of the two valid values
    noon = h.hourly[datetime(2026, 1, 15, 12, 0)]
    assert noon["tss"] > -0.5  # melting surface at midday


def test_parse_smet_ignores_bad_rows():
    h = parse_smet(SMET + "garbage line\n2026-01-15T12:00:00Z 1 2\n")
    assert len(h.times) == 5


def test_parse_history_detects_gzip_and_smet():
    h = parse_history(gzip.compress(SMET.encode()), station="gz")
    assert h is not None and len(h.times) == 5 and h.station == "gz"
    assert parse_history(b"<html>not data</html>") is None


def test_parse_geosphere_timeseries():
    data = {
        "type": "FeatureCollection",
        "timestamps": ["2026-01-15T05:00:00+00:00", "2026-01-15T05:10:00+00:00", "2026-01-15T11:00:00+00:00"],
        "features": [{"type": "Feature", "properties": {"station": "11149", "parameters": {
            "TL": {"name": "Lufttemperatur", "unit": "°C", "data": [-8.0, -8.2, 1.5]},
            "SCHNEE": {"name": "Schneehöhe", "unit": "cm", "data": [120, 120, None]},
        }}}],
    }
    h = parse_history(json.dumps(data).encode())
    assert h is not None and h.station == "11149"
    assert h.values["TA"] == [-8.0, -8.2, 1.5] and h.values["HS"][2] is None
    six = h.hourly[datetime(2026, 1, 15, 6, 0)]
    assert abs(six["ta"] - (-8.1)) < 1e-9 and six["tss"] is None and six["hs"] == 120
    assert parse_geosphere({"timestamps": [], "features": []}).times == []
