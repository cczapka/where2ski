from datetime import date, datetime, timedelta

from where2ski_pipeline.model.snow import (
    ASPECTS, aspect_sun_factor, assess_day, assess_resort_day, normalise_rose,
)
from where2ski_pipeline.sources.smet import StationHistory as SmetHistory
from .conftest import TODAY, daytime_sun, make_series


def snow_on(day, cm_per_hour=2.0):
    return lambda t: cm_per_hour if t.date() == day and 6 <= t.hour < 18 else 0.0


def test_sun_factor_seasonal():
    assert aspect_sun_factor("S", date(2026, 1, 10)) == 1.0
    assert aspect_sun_factor("N", date(2026, 1, 10)) == 0.15
    assert aspect_sun_factor("N", date(2026, 4, 10)) > 0.7
    assert normalise_rose(None) == {a: 0.125 for a in ASPECTS}
    assert abs(sum(normalise_rose({"N": 3, "S": 1}).values()) - 1.0) < 1e-9


def test_north_keeps_powder_while_south_crusts():
    # snowfall 4 days ago, cold nights, mild sunny days: sun load decides the surface
    def temp(t):
        return -1.0 if 10 <= t.hour < 16 else -8.0

    mid = make_series(temp=temp, snowfall=snow_on(TODAY - timedelta(days=4)), sun=lambda t: daytime_sun(t, 7))
    top = make_series(temp=lambda t: -6.0, gust=lambda t: 15.0)
    rose = {"N": 0.5, "S": 0.5}
    a = assess_resort_day(mid, top, TODAY, TODAY, rose)
    assert a.by_aspect["N"]["state"] == "settled_powder"
    assert a.by_aspect["S"]["state"] == "crust"
    assert a.best_aspect == "N"
    assert 0.5 < a.value_freeride < 0.9  # blend of the two faces with a bonus for the good one
    assert any("best aspect N" in r for r in a.reasons)


def test_avalanche_capping_lowers_flagged_aspects():
    mid = make_series(temp=lambda t: -8.0, snowfall=snow_on(TODAY - timedelta(days=1)))
    top = make_series(temp=lambda t: -12.0, gust=lambda t: 20.0)
    free = assess_resort_day(mid, top, TODAY, TODAY, None)
    capped = assess_resort_day(mid, top, TODAY, TODAY, None, flagged_aspects={"N", "NE", "E"})
    assert free.value_freeride == 1.0
    assert capped.value_freeride < free.value_freeride
    assert capped.by_aspect["N"]["capped"] and capped.by_aspect["N"]["value_freeride"] == 0.2
    assert not capped.by_aspect["S"]["capped"]
    assert capped.value_piste == free.value_piste  # piste ignores avalanche problems


def test_station_history_overrides_melt_detection():
    # model says cold all day, but the station measured a melting surface for six hours
    mid = make_series(temp=lambda t: -4.0, snowfall=snow_on(TODAY - timedelta(days=3)))
    top = make_series(temp=lambda t: -6.0)
    hist = SmetHistory(station="TEST")
    start = datetime.combine(TODAY - timedelta(days=2), datetime.min.time())
    for h in range(48):
        t = start + timedelta(hours=h)
        hist.times.append(t)
    hist.values = {"TSS": [(0.0 if 10 <= t.hour < 16 else -6.0) for t in hist.times],
                   "TA": [1.0 if 10 <= t.hour < 16 else -3.0 for t in hist.times]}
    hist.build_hourly()
    without = assess_day(mid, top, TODAY, TODAY)
    with_hist = assess_day(mid, top, TODAY, TODAY, history=hist)
    assert without.melt_hours == 0 and without.state == "settled_powder"
    assert with_hist.melt_hours >= 10 and with_hist.refreeze
    assert with_hist.state in ("crust", "corn")
