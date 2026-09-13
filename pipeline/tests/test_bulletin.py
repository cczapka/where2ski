from where2ski_pipeline.sources.bulletin import find_micro_region, parse_caaml, parse_ratings
from .conftest import CAAML, MICRO_REGIONS


def test_parse_caaml_levels_by_elevation():
    parsed = parse_caaml(CAAML, source="test")
    b = parsed["AT-07-14"]
    assert b.level_at(2500) == 3
    assert b.level_at(1800) == 2
    assert [p.type for p in b.problems_at(2500)] == ["wind_slab"]
    assert b.problems_at(1500) == []
    assert b.tendency == "steady"
    assert b.valid_date == "2026-01-15"
    assert b.problems[0].public()["elevation"] == "above 2200 m"


def test_parse_ratings_best_effort():
    parsed = parse_ratings({"DE-BY-10": 2, "DE-BY-11": {"am": "moderate", "pm": 3}, "junk": "x"}, source="t")
    assert parsed["DE-BY-10"].level_at(1000) == 2
    assert parsed["DE-BY-11"].level_at(1000) == 3
    assert "junk" not in parsed


def test_find_micro_region():
    assert find_micro_region(MICRO_REGIONS["features"], 47.213, 11.011) == "AT-07-14"
    assert find_micro_region(MICRO_REGIONS["features"], 48.0, 11.5) is None
