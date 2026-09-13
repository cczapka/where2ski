from where2ski_pipeline.registry import Resort
from where2ski_pipeline.sources.stations import flatten, map_stations, parse_station_feature, weighted
from .conftest import STATIONS_GEOJSON


def test_flatten_nested():
    flat = flatten({"a": {"b": 1, "c": [{"d": 2}]}})
    assert flat == {"a.b": 1, "a.c.0.d": 2}


def test_parse_station_tolerant_keys():
    st = parse_station_feature(STATIONS_GEOJSON["features"][0])
    assert st.name == "Kühtai Test"
    assert st.elevation == 2050  # from the z coordinate
    assert st.hs == 112 and st.hn24 == 18 and st.hn72 == 30
    assert st.t_air == -6.5 and st.t_surface == -9.0 and st.gust == 28
    assert st.time.startswith("2026-01-15")
    st2 = parse_station_feature(STATIONS_GEOJSON["features"][1])
    assert st2.hs == 60.0 and st2.t_air == -12.0  # numeric strings accepted


def test_map_stations_filters_distance_and_elevation():
    resort = Resort(id="k", name="K", region="AT-07", lat=47.213, lon=11.011,
                    elevation={"base": 2020, "mid": 2300, "top": 2520})
    stations = [parse_station_feature(f) for f in STATIONS_GEOJSON["features"]]
    mapped = map_stations(resort, stations)
    assert [m.station.name for m in mapped] == ["Kühtai Test"]
    assert abs(sum(m.weight for m in mapped) - 1.0) < 1e-9
    assert weighted(mapped, "hs") == 112
    assert weighted(mapped, "wind") is None
