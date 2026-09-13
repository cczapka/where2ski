from where2ski_pipeline.registry import Resort
from where2ski_pipeline.sources.stations import flatten, map_stations, parse_station_feature, weighted
from .conftest import STATIONS_GEOJSON


def test_flatten_nested():
    flat = flatten({"a": {"b": 1, "c": [{"d": 2}]}})
    assert flat == {"a.b": 1, "a.c.0.d": 2}


def test_parse_station_converts_si_units():
    st = parse_station_feature(STATIONS_GEOJSON["features"][0])
    assert st.name == "Kühtai Test"
    assert st.elevation == 2050  # from the z coordinate
    assert abs(st.hs - 112) < 1e-6 and abs(st.hn24 - 18) < 1e-6 and abs(st.hn72 - 30) < 1e-6
    assert abs(st.t_air - (-6.5)) < 1e-6 and abs(st.t_surface - (-9.0)) < 1e-6
    assert abs(st.gust - 28.08) < 1e-6 and abs(st.wind - 10.8) < 1e-6
    assert st.time.startswith("2026-01-15") and st.micro_region == "AT-07-14"
    st2 = parse_station_feature(STATIONS_GEOJSON["features"][1])
    assert abs(st2.hs - 60.0) < 1e-6 and abs(st2.t_air - (-12.0)) < 1e-6  # numeric strings accepted
    assert st2.hn24 == 0.0  # settling (negative difference) is not new snow
    assert st2.elevation == 2950


def test_map_stations_filters_distance_and_elevation():
    resort = Resort(id="k", name="K", region="AT-07", lat=47.213, lon=11.011,
                    elevation={"base": 2020, "mid": 2300, "top": 2520})
    stations = [parse_station_feature(f) for f in STATIONS_GEOJSON["features"]]
    mapped = map_stations(resort, stations)
    assert [m.station.name for m in mapped] == ["Kühtai Test"]
    assert abs(sum(m.weight for m in mapped) - 1.0) < 1e-9
    assert abs(weighted(mapped, "hs") - 112) < 1e-6
    assert weighted(mapped, "t_surface") is not None
