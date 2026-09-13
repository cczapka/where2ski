from datetime import timedelta

from where2ski_pipeline.model.snow import assess_day, day_weather, last_snowfall_end
from .conftest import TODAY, daytime_sun, make_series


def snow_on(day, cm_per_hour=2.0):
    return lambda t: cm_per_hour if t.date() == day and 6 <= t.hour < 18 else 0.0


def test_fresh_powder_after_cold_snowfall():
    mid = make_series(temp=lambda t: -8.0, snowfall=snow_on(TODAY - timedelta(days=1)))
    top = make_series(temp=lambda t: -12.0, gust=lambda t: 20.0)
    a = assess_day(mid, top, TODAY, TODAY)
    assert a.hn24 >= 10 and a.hn72 >= 20
    assert a.state == "fresh_powder"
    assert a.value_freeride == 1.0
    assert last_snowfall_end(mid, mid.times[-1]) is not None


def test_wind_affected_when_gusty():
    mid = make_series(temp=lambda t: -8.0, snowfall=snow_on(TODAY - timedelta(days=1)))
    top = make_series(temp=lambda t: -12.0, gust=lambda t: 70.0)
    assert assess_day(mid, top, TODAY, TODAY).state == "wind_affected"


def test_crust_after_melt_and_refreeze():
    # snowfall 5 days ago, then warm sunny afternoons with cold nights
    def temp(t):
        return 3.0 if 11 <= t.hour < 17 else -4.0

    mid = make_series(temp=temp, snowfall=snow_on(TODAY - timedelta(days=5)), sun=lambda t: daytime_sun(t, 6))
    top = make_series(temp=lambda t: -3.0)
    a = assess_day(mid, top, TODAY, TODAY)
    assert a.melt_hours > 2 and a.refreeze
    # three or more melt-freeze cycles with a sunny forecast turn into corn
    assert a.state in ("crust", "corn")
    if a.cycles >= 3:
        assert a.state == "corn"


def test_rain_soaked():
    mid = make_series(temp=lambda t: 2.0, snowfall=snow_on(TODAY - timedelta(days=3)),
                      rain=lambda t: 1.0 if t.date() == TODAY - timedelta(days=1) else 0.0)
    top = make_series(temp=lambda t: 0.0)
    assert assess_day(mid, top, TODAY, TODAY).state == "rain_soaked"


def test_station_values_override_today_only():
    mid = make_series(temp=lambda t: -5.0)
    top = make_series(temp=lambda t: -8.0)
    a = assess_day(mid, top, TODAY, TODAY, station_hs=95, station_hn={"hn24": 12, "hn48": None, "hn72": 20})
    assert a.hs == 95 and a.hs_source == "station" and a.hn24 == 12 and a.hn72 == 20
    b = assess_day(mid, top, TODAY + timedelta(days=2), TODAY, station_hs=95)
    assert b.hs_source == "station+forecast" and b.hn24 == 0


def test_glacier_floor_and_model_depth():
    mid = make_series(temp=lambda t: -5.0, snow_depth=lambda t: 0.4)
    top = make_series(temp=lambda t: -8.0)
    a = assess_day(mid, top, TODAY, TODAY)
    assert a.hs == 40 and a.hs_source == "model"
    g = assess_day(mid, top, TODAY, TODAY, glacier=True)
    assert g.hs == 100 and g.hs_source == "glacier"


def test_day_weather_aggregates():
    base = make_series(elevation=800, temp=lambda t: 2.0, low_cloud=lambda t: 90.0)
    mid = make_series(elevation=1500, temp=lambda t: -3.0, sun=lambda t: daytime_sun(t, 7))
    top = make_series(elevation=2000, temp=lambda t: -1.0, gust=lambda t: 55.0)
    w = day_weather(base, mid, top, TODAY)
    assert w.sun_hours == 7.0
    assert w.gust_max_top == 55.0
    assert w.low_cloud_base_pct == 90.0
    assert w.t_mean_day_top == -1.0
