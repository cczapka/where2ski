from where2ski_pipeline import config
from where2ski_pipeline.model import precip
from .conftest import make_series


def test_phase_and_density():
    assert precip.snow_share(-2.0) == 1.0 and precip.snow_share(2.0) == 0.0
    assert abs(precip.snow_share(0.75) - 0.5) < 1e-9
    # 0.84 cm per mm at 0 °C and about 1.33 at -5 °C (docs/PLAN.md 7.3), against the service's fixed 0.7
    assert abs(100.0 / precip.density(0.0, -0.5) - 0.84) < 0.01
    assert abs(100.0 / precip.density(-5.0, -5.5) - 1.33) < 0.02
    # dry air: the wet-bulb is well below the air temperature, so 1 °C air can still give snow
    assert precip.wet_bulb(1.0, 60.0) < 0.0
    assert precip.snow_cm(5.4, -8.2, 90.0)[0] > 6.0  # 13 Nov Hintertux: 5.4 mm at -8 °C, service said 0.1 cm


def test_derive_keeps_both_and_switch_decides(monkeypatch):
    s = make_series(temp=lambda t: -6.0, snowfall=lambda t: 0.1)
    s.values["precipitation"] = [1.0] * len(s.times)
    s.values["relative_humidity_2m"] = [90.0] * len(s.times)
    monkeypatch.setattr(config, "SNOWFALL_SOURCE", "api")
    precip.derive(s)
    assert s.values["snowfall"][0] == 0.1 and s.values["snow_derived"][0] > 1.2
    monkeypatch.setattr(config, "SNOWFALL_SOURCE", "derived")
    precip.derive(s)
    assert s.values["snowfall"][0] == s.values["snow_derived"][0] and s.values["snow_api"][0] == 0.1


def test_snow_line_between_bands():
    bands = {
        "base": make_series(elevation=1000, temp=lambda t: 5.0),
        "mid": make_series(elevation=2000, temp=lambda t: -1.0),
        "top": make_series(elevation=2800, temp=lambda t: -6.0),
    }
    for b in bands.values():
        b.values["relative_humidity_2m"] = [100.0] * len(b.times)
    line = precip.snow_line(bands)
    # wet-bulb equals air temperature at 100 %: 1 °C lies a third of the way from 2000 m down to 1000 m
    assert 1600 <= line[0] <= 1700
    assert bands["mid"].values["snow_line_m"] is line
