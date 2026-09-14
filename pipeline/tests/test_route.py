from datetime import date, datetime, timedelta

from where2ski_pipeline.registry import Resort
from where2ski_pipeline.sources.openmeteo import HourlySeries
from where2ski_pipeline.sources.route import (
    RoadPoint, road_factor, road_report, waypoints_for,
)

DAY = date(2026, 1, 15)


def resort(lat, lon, links=None):
    return Resort(id="x", name="x", region="AT-07", lat=lat, lon=lon,
                  elevation={"base": 1000, "mid": 1500, "top": 2000}, links=links or {})


def series(snow_per_hour=0.0, rain_per_hour=0.0, temp=-3.0):
    start = datetime.combine(DAY, datetime.min.time())
    times = [start + timedelta(hours=h) for h in range(24)]
    return HourlySeries(times=times, values={
        "snowfall": [snow_per_hour] * 24,
        "rain": [rain_per_hour] * 24,
        "temperature_2m": [temp] * 24,
        "freezing_level_height": [800.0] * 24,
    })


def test_corridor_picks_the_pass_on_the_way():
    # Ehrwald: the drive from Munich goes past Garmisch and over the Fernpass
    names = [w[0] for w in waypoints_for(resort(47.399, 10.910))]
    assert "Garmisch / Griesen" in names and "Fernpass" in names
    # Berchtesgaden: motorway only, no alpine pass in the corridor
    assert waypoints_for(resort(47.592, 13.022)) == []
    # at most three, nearest to the line first
    assert len(waypoints_for(resort(46.98, 10.30))) <= 3


def test_pinned_waypoints_override_the_corridor():
    r = resort(47.166, 11.864, links={"road_waypoints": ["Achenpass"]})
    assert [w[0] for w in waypoints_for(r)] == ["Achenpass"]
    assert waypoints_for(resort(47.166, 11.864, links={"road_waypoints": []})) == []


def test_road_report_picks_the_worst_waypoint():
    points = [
        RoadPoint("Achenpass", 941, series(snow_per_hour=0.2)),
        RoadPoint("Gerlospass", 1531, series(snow_per_hour=2.0)),
    ]
    rep = road_report(points, DAY)
    assert rep["waypoint"] == "Gerlospass" and rep["elevation"] == 1531
    assert rep["snowfall_cm"] == 12.0  # 6 morning hours
    assert rep["points"] == 2 and rep["t_min"] == -3.0


def test_road_factor_scale():
    assert road_factor(None, expected=False) == 1.0   # no pass on the drive
    assert road_factor(None, expected=True) == 0.9    # pass exists but no data
    assert road_factor({"snowfall_cm": 0.0}) == 1.0
    assert road_factor({"snowfall_cm": 20.0}) == 0.2
    mid = road_factor({"snowfall_cm": 7.75})
    assert 0.55 < mid < 0.65
