"""WP4 scenario tests (docs/PLAN.md 8.4), synthetic weather at 47.2° N."""

from datetime import date, datetime, timedelta

from where2ski_pipeline.model import surface
from where2ski_pipeline.model.solar import hourly_radiation
from .conftest import TODAY, daytime_sun, make_series

LAT, LON = 47.2, 11.0
D0 = datetime.combine(TODAY, datetime.min.time())  # series run from TODAY-10 d to TODAY+10 d


def series(today=TODAY, temp=lambda t: -8.0, snowfall=lambda t: 0.0, rain=lambda t: 0.0, sun=lambda t: 0.0,
           gust=lambda t: 15.0, cloud=lambda t: 0.0, wind_from=270.0, rh=80.0):
    s = make_series(today=today, temp=temp, snowfall=snowfall, rain=rain, sun=sun, gust=gust, low_cloud=cloud)
    s.values["wind_direction_10m"] = [wind_from] * len(s.times)
    s.values["relative_humidity_2m"] = [rh] * len(s.times)
    return s


def at(states, when):
    return next(st for st in states if st.time == when)


def run(s, aspect, top=None):
    return surface.simulate(s, top or s, aspect, LAT, LON, radiation=hourly_radiation(s, LAT, LON))


def storm(t, start=D0 - timedelta(days=2), hours=12, cm=2.0):
    return cm if start <= t < start + timedelta(hours=hours) else 0.0


def test_cold_storm_gives_powder():
    s = series(snowfall=storm)
    st = at(run(s, "N"), D0 + timedelta(hours=10))
    assert st.kind == "powder" and 13 <= st.new_cm <= 20  # 24 cm fallen, settled for two days
    assert surface.label(st) == "settled_powder" or surface.label(st) == "fresh_powder"
    assert surface.value(st, "freeride") > 0.7  # 16 cm settled: 0.5 at 5 cm rising to 1.0 at 25 cm


def test_storm_then_warm_sun_crusts_south_keeps_north():
    # 24 cm, then two clear days at +4 °C by day and -6 °C at night
    def temp(t):
        if t < D0 - timedelta(days=2) + timedelta(hours=12):
            return -8.0
        return 4.0 if 10 <= t.hour < 16 else -6.0
    s = series(snowfall=storm, temp=temp, sun=lambda t: daytime_sun(t, 7))
    when = D0 + timedelta(hours=9)
    south, north = at(run(s, "S"), when), at(run(s, "N"), when)
    assert south.kind == "crust", south
    assert north.kind == "powder", north


def _crust_then_snow(cm):
    # rain crust from rain at +3 °C, a frost, then cm of cold snow
    rain_day = D0 - timedelta(days=4)
    snow_start = D0 - timedelta(days=1)

    def temp(t):
        return 3.0 if rain_day <= t < rain_day + timedelta(hours=10) else -8.0
    s = series(temp=temp, rain=lambda t: 1.0 if rain_day <= t < rain_day + timedelta(hours=6) else 0.0,
               snowfall=lambda t: (cm / 6.0) if snow_start <= t < snow_start + timedelta(hours=6) else 0.0)
    return at(run(s, "N"), D0 + timedelta(hours=10))


def test_dust_on_crust_and_powder_on_crust():
    thin = _crust_then_snow(3.0)
    assert thin.under == "ice" and surface.label(thin) == "dust_on_crust", thin
    assert surface.value(thin, "freeride") == 0.25
    deep = _crust_then_snow(20.0)
    assert deep.kind == "powder" and surface.label(deep) != "dust_on_crust" and surface.value(deep, "freeride") > 0.7


def test_clear_spring_days_give_a_late_morning_corn_window():
    spring = date(2027, 4, 10)
    d0 = datetime.combine(spring, datetime.min.time())

    def temp(t):
        return 6.0 if 11 <= t.hour < 17 else -4.0
    s = series(today=spring, temp=temp, sun=lambda t: daytime_sun(t, 9), rh=50.0)
    states = run(s, "SE")
    early, late_morning = at(states, d0 + timedelta(hours=8)), at(states, d0 + timedelta(hours=11))
    assert early.kind == "corn_frozen", early
    assert late_morning.kind == "corn_soft", late_morning
    assert surface.value(late_morning, "freeride") > surface.value(early, "freeride")


def test_rain_then_frost_gives_rain_crust():
    wet_day = D0 - timedelta(days=2)
    s = series(temp=lambda t: 2.0 if t < wet_day + timedelta(hours=8) else -7.0,
               rain=lambda t: 1.5 if wet_day <= t < wet_day + timedelta(hours=8) else 0.0, rh=95.0)
    st = at(run(s, "N"), D0 + timedelta(hours=10))
    assert st.kind == "rain_crust" and surface.value(st, "freeride") == 0.05


def test_north_west_wind_packs_north_west_and_loads_south_east():
    s = series(snowfall=storm, gust=lambda t: 70.0 if D0 - timedelta(days=2) <= t < D0 - timedelta(days=1) else 15.0,
               wind_from=315.0)
    when = D0 + timedelta(hours=10)
    nw, se, n0 = at(run(s, "NW"), when), at(run(s, "SE"), when), at(run(series(snowfall=storm), "SE"), when)
    assert nw.kind == "wind_packed" and nw.new_cm < n0.new_cm * 0.6
    assert se.loaded and se.new_cm > n0.new_cm * 1.2


def test_long_windy_storm_stays_bounded():
    # 48 hours of snow in a gale: lee and windward must scale the fallen snow, not compound every hour
    long_storm = lambda t: storm(t, start=D0 - timedelta(days=4), hours=48, cm=1.0)  # noqa: E731
    s = series(snowfall=long_storm, gust=lambda t: 80.0, wind_from=315.0)
    when = D0 - timedelta(hours=1)
    se, nw = at(run(s, "SE"), when), at(run(s, "NW"), when)
    assert se.deposited_cm <= 1.3 * 48 + 1e-6 and se.new_cm <= 1.3 * 48
    assert 0 < nw.new_cm < se.new_cm and nw.kind == "wind_packed" and se.loaded
