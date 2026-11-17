"""WP1: stale readings, implausible values, glacier depth, missing bulletins, opening dates."""

from datetime import date, datetime, timezone

from where2ski_pipeline.model import score as sc
from where2ski_pipeline.registry import Resort
from where2ski_pipeline.run import is_limited, is_open
from where2ski_pipeline.sources.bulletin import fetch_bulletins
from where2ski_pipeline.http import Http
from where2ski_pipeline.sources.stations import (MappedStation, Station, combine, dedupe, mark_age,
                                                 quality_control)
from .test_score import snow, weather


def st(name, hs=None, hn24=None, t_air=None, time="2026-10-22T04:30:00Z", **kw):
    return Station(name=name, lat=46.86, lon=11.03, elevation=2550, hs=hs, hn24=hn24, hn48=hn24, hn72=hn24,
                   t_air=t_air, time=time, **kw)


def mapped(*stations):
    return [MappedStation(station=s, distance_km=1.0, weight=1.0 / len(stations)) for s in stations]


def test_stale_readings_are_not_used():
    now = datetime(2026, 11, 10, 3, 34, tzinfo=timezone.utc)
    frozen = st("Tuxerjoch", hs=27.0, hn24=0.0, t_air=-3.0, time="2026-11-05T09:50:00.000Z")
    fresh = st("Eissee", hs=20.0, t_air=-1.0, time="2026-11-10T03:10:00Z")
    no_time = st("Penken", hs=10.0, time=None)
    mark_age([frozen, fresh, no_time], now)
    assert frozen.stale and frozen.hs is None and frozen.t_air is None and round(frozen.age_h) == 114
    assert {"field": "hs", "value": 27.0, "rule": "stale"} in frozen.rejected
    assert not fresh.stale and fresh.hs == 20.0 and abs(fresh.age_h - 0.4) < 0.01
    assert no_time.stale and no_time.hs is None


def test_obergurgl_spike_is_rejected():
    # 22 Oct 2026: Äußeres Hochebenkar jumped from no reading to 278 cm, "277.5 cm new snow"
    out = quality_control(mapped(st("Sonnbergalm", hs=19.8, hn24=15.0), st("Rosskar", hs=24.7, hn24=4.3),
                                 st("Äußeres Hochebenkar", hs=278.0, hn24=277.5)))
    spike = out[2].station
    assert spike.hs is None and spike.hn24 is None
    assert {r["rule"] for r in spike.rejected} == {"limit_24h"}
    assert combine(out, "hs") == 22.25  # two left, within a factor of two: their mean
    assert out[0].station.hn24 == 15.0


def test_unconfirmed_large_new_snow_is_rejected_and_confirmed_is_kept():
    alone = quality_control(mapped(st("A", hs=90.0, hn24=70.0), st("B", hs=20.0, hn24=5.0)))
    assert alone[0].station.hn24 is None and alone[0].station.rejected[0]["rule"] == "agreement"
    both = quality_control(mapped(st("A", hs=90.0, hn24=70.0), st("B", hs=60.0, hn24=35.0)))
    assert both[0].station.hn24 == 70.0


def test_continuity_against_yesterday():
    jump = quality_control(mapped(st("A", hs=150.0, hn24=10.0)), yesterday_hs={"A": 40.0}, precip_24h_mm=5.0)
    assert jump[0].station.hs is None and jump[0].station.rejected[0]["rule"] == "continuity"
    storm = quality_control(mapped(st("A", hs=150.0, hn24=10.0)), yesterday_hs={"A": 40.0}, precip_24h_mm=45.0)
    assert storm[0].station.hs == 150.0


def test_bare_ground_and_exclusion():
    # Saalbach, October 2026: 38-40 cm "snow" at 9-12 °C air temperature, model without snow
    out = quality_control(mapped(st("Wlv Lahnkendllawine", hs=38.0, t_air=9.2), st("Reckmoos", hs=None, t_air=10.6)),
                          model_depth_cm=0.0, exclude=["Reckmoos"])
    assert out[0].station.hs == 0.0 and out[0].station.rejected[0]["rule"] == "bare_ground"
    assert out[1].station.t_air is None and out[1].station.rejected[0]["rule"] == "excluded"
    cold = quality_control(mapped(st("Wlv Lahnkendllawine", hs=38.0, t_air=2.0)), model_depth_cm=0.0)
    assert cold[0].station.hs == 38.0


def test_quality_control_does_not_touch_shared_stations():
    shared = st("A", hs=278.0, hn24=277.5)
    quality_control(mapped(shared))
    assert shared.hs == 278.0 and shared.rejected == []


def test_combine():
    assert combine(mapped(st("A", hs=10.0), st("B", hs=50.0), st("C", hs=30.0)), "hs") == 30.0
    assert combine(mapped(st("A", hs=40.0), st("B", hs=50.0)), "hs") == 45.0
    assert combine(mapped(st("A", hs=10.0), st("B", hs=50.0)), "hs") == 10.0
    assert combine(mapped(st("A")), "hs") is None


def test_dedupe_keeps_the_record_with_values():
    a = st("Pitztaler Gletscher", hs=46.0, t_air=-4.3, time="2026-11-16T12:40:00Z")
    b = st("Pitztaler Gletscher", time="2026-11-16T23:00:00Z")
    assert dedupe([b, a]) == [a]


def test_glacier_blockers():
    g = dict(glacier=True, mid_elevation=2800)
    assert sc.blockers("freeride", snow(hs=200), weather(), 2, True, glacier_top_hs=None, **g) == \
        ["snow depth over the glacier ice is not measured"]
    assert "crevasses" in sc.blockers("freeride", snow(hs=200), weather(), 2, True, glacier_top_hs=80, **g)[0]
    assert sc.blockers("freeride", snow(hs=10), weather(), 2, True, glacier_top_hs=150, **g) == []
    # piste on a glacier is not blocked by thin natural snow: the base is ice and the operator decides
    assert sc.blockers("piste", snow(hs=10), weather(), 2, True, **g) == []


def test_alpine_and_low_freeride_minimum():
    assert sc.blockers("freeride", snow(hs=70), weather(), 2, True, mid_elevation=1500) == []
    assert "needs 80" in sc.blockers("freeride", snow(hs=70), weather(), 2, True, mid_elevation=2300)[0]


def test_opening_dates_and_limited_opening():
    r = Resort(id="k", name="K", region="AT-07", lat=0, lon=0, elevation={"base": 1, "mid": 2, "top": 3},
               season={"open": "2026-11-06", "close": "2027-04-18", "limited_until": "2026-12-04"})
    assert not is_open(r, date(2026, 11, 5)) and is_open(r, date(2026, 11, 6))
    assert is_limited(r, date(2026, 11, 20)) and not is_limited(r, date(2026, 12, 5))
    assert not is_open(r, date(2027, 4, 19)) and not is_limited(r, date(2026, 11, 1))


def test_bulletin_not_published_versus_failed(tmp_path):
    (tmp_path / "eaws_ratings_2026-11-01.json.error").write_text("404 Client Error: Not Found for url")
    _, status = fetch_bulletins(Http(offline_dir=tmp_path), "DE-BY", "2026-11-01")
    assert status["reason"] == "not_published"
    (tmp_path / "eaws_ratings_2026-11-02.json.error").write_text("Tunnel connection failed: 403 Forbidden")
    _, status = fetch_bulletins(Http(offline_dir=tmp_path), "DE-BY", "2026-11-02")
    assert status["reason"] == "failed"
