import csv
import json
from datetime import datetime, timezone

from tools.snapshots_to_archive import convert
from tools.verify import derived_snow_cm, score, wet_bulb
from where2ski_pipeline.archive import parse_rejected, read_rows, write_archive, yesterday_hs
from where2ski_pipeline.run import run
from .conftest import NOW, TODAY


def test_archive_written_once_per_day_and_read_back(registry_path, offline_dir, tmp_path):
    archive = tmp_path / "archive"
    early = datetime(2026, 1, 15, 3, 17, tzinfo=timezone.utc)
    latest = run(registry=registry_path, out_dir=tmp_path / "o", offline_dir=offline_dir, today=TODAY, now=early,
                 archive_dir=archive)
    assert latest["status"]["archive"] == {"forecast": 0, "obs": 0}  # before 05:00 UTC nothing is written
    latest = run(registry=registry_path, out_dir=tmp_path / "o", offline_dir=offline_dir, today=TODAY, now=NOW,
                 archive_dir=archive)
    assert latest["status"]["archive"]["forecast"] == 20  # two resorts, ten lead days
    assert latest["status"]["archive"]["obs"] == 1
    again = write_archive(archive, latest, datetime(2026, 1, 15, 9, 17, tzinfo=timezone.utc))
    assert again == {"forecast": 0, "obs": 0}
    midday = write_archive(archive, latest, datetime(2026, 1, 15, 12, 17, tzinfo=timezone.utc))
    assert midday == {"forecast": 0, "obs": 1}
    late = write_archive(archive, {**latest, "today": "2026-01-16"}, datetime(2026, 1, 15, 23, 17, tzinfo=timezone.utc))
    assert late == {"forecast": 0, "obs": 0}  # already tomorrow in local time: wait for the morning run
    rows = read_rows(archive, "forecast")
    assert {r["lead"] for r in rows} == {str(i) for i in range(10)}
    assert yesterday_hs(archive, TODAY.replace(day=16)) == {"kuehtai": {"Kühtai Test": 112.0}}


def test_rejected_round_trip():
    assert parse_rejected("hs=278.0:limit_24h;hn24=7.4:stale") == [
        {"field": "hs", "value": 278.0, "rule": "limit_24h"}, {"field": "hn24", "value": 7.4, "rule": "stale"}]


def _snapshot(day, gen, hn24, fc, time):
    st = {"name": "S", "lat": 47.0, "lon": 11.0, "elevation": 2300, "hs": 50.0, "hn24": hn24, "hn48": hn24,
          "hn72": hn24, "t_air": -5.0, "t_surface": -8.0, "gust": 10.0, "time": time}
    today = {"date": day, "lead": 0, "scores": {"freeride": 50.0, "piste": 50.0}, "confidence": 0.9,
             "snow": {"state": "hardpack", "hs": 50, "hs_source": "station"},
             "weather": {"snowfall_cm": fc, "precip_mm": fc, "t_mean_day_mid": -4.0, "sun_hours": 3.0}}
    return {"date": day, "generated_at": gen, "resorts": {"kuehtai": {"stations": [st], "today": today}}}


def test_converter_and_score(tmp_path, registry_path):
    snaps = tmp_path / "snaps"
    snaps.mkdir()
    days = [("2026-11-01", "2026-11-01T05:00:00+00:00", 0.0, 8.0, "2026-11-01T04:40:00Z"),
            ("2026-11-02", "2026-11-02T05:00:00+00:00", 12.0, 0.0, "2026-11-02T04:40:00Z"),   # hit for 1 Nov
            ("2026-11-03", "2026-11-03T05:00:00+00:00", 9.0, 0.0, "2026-11-02T04:40:00Z")]    # stale: no obs
    for d, g, hn, fc, t in days:
        (snaps / f"{d}.json").write_text(json.dumps(_snapshot(d, g, hn, fc, t)))
    archive = tmp_path / "archive"
    counts = convert(snaps, archive)
    assert counts == {"days": 3, "forecast": 3, "obs": 3, "rejected": 0}
    with (archive / "obs-2026-11.csv").open() as fh:
        obs = list(csv.DictReader(fh))
    assert obs[2]["hn24"] == "" and "hn24=9.0:stale" in obs[2]["rejected"]
    result = score(archive, registry=registry_path)
    lead0 = result["snowfall"]["0"]
    assert lead0["n"] == 1 and lead0["categories"][0]["hits"] == 1  # 2 Nov is not scored: its observation is stale


def test_snow_derivation():
    assert abs(wet_bulb(20.0, 50.0) - 13.7) < 0.1  # Stull's worked example
    assert derived_snow_cm(10.0, 5.0, 90.0) == 0.0
    cold = derived_snow_cm(10.0, -5.0, 90.0)
    assert 12.5 < cold < 14.0  # about 1.3 cm per mm at -5 °C, against the fixed 0.7 of the weather service
