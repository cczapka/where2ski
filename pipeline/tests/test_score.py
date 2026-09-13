from where2ski_pipeline import config
from where2ski_pipeline.model import score as sc
from where2ski_pipeline.model.snow import DayWeather, SnowAssessment


def snow(**kw):
    base = dict(state="fresh_powder", value_freeride=1.0, value_piste=0.9, hn24=20, hn48=30, hn72=35, hs=120,
                hs_source="station", days_since_snow=1, melt_hours=0, sun_load=0, cycles=0, refreeze=True,
                rain_hours=0, gust_max=20)
    base.update(kw)
    return SnowAssessment(**base)


def weather(**kw):
    base = dict(sun_hours=7, t_min_mid=-10, t_max_mid=-3, t_mean_day_mid=-5, t_mean_day_top=-8, t_mean_day_base=-1,
                gust_max_top=20, precip_mm=0, snowfall_cm=0, low_cloud_pct=10, low_cloud_base_pct=10,
                freezing_level_m=800, visibility_m=30000)
    base.update(kw)
    return DayWeather(**base)


def test_perfect_day_scores_high_in_both_modes():
    f = sc.build_factors(snow(), weather(), level=1, travel_min=60, crowd=1.0)
    assert sc.score("freeride", f) > 90
    assert sc.score("piste", f) > 90
    assert "powder_day" in sc.badges(snow(), weather())
    assert "bluebird" in sc.badges(snow(), weather())


def test_blockers():
    assert "avalanche danger level 4" in sc.blockers("freeride", snow(), weather(), level=4, is_open=True)
    assert sc.blockers("piste", snow(), weather(), level=4, is_open=True) == []
    assert any("thin" in b for b in sc.blockers("piste", snow(hs=20), weather(), None, True))
    assert any("closed" in b for b in sc.blockers("piste", snow(), weather(), None, False))


def test_factor_shapes():
    assert sc.wind_factor(weather(gust_max_top=90)) == 0.0
    assert sc.wind_factor(weather(gust_max_top=45)) == 0.7
    assert sc.temperature_factor(weather(t_mean_day_mid=8)) == 0.0
    assert sc.temperature_factor(weather(t_mean_day_mid=-20)) == 0.2
    assert sc.travel_factor(60) == 1.0 and sc.travel_factor(150) == 0.4
    assert sc.avalanche_factor(None) == 0.7
    assert sc.sun_vis_factor(weather(sun_hours=0, low_cloud_pct=100)) == 0.0


def test_custom_weights_and_confidence():
    f = sc.build_factors(snow(), weather(sun_hours=0, low_cloud_pct=100), level=2, travel_min=120, crowd=0.7)
    sunny_only = {k: (1 if k == "sun_vis" else 0) for k in config.WEIGHTS["piste"]}
    assert sc.score("piste", f, sunny_only) == 0.0
    assert sc.confidence(0, True, True) == 1.0
    assert sc.confidence(9, False, False) < 0.2
    assert "inversion" in sc.badges(snow(), weather(low_cloud_base_pct=90, t_mean_day_top=-2, t_mean_day_base=-2))
