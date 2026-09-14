import json

from where2ski_pipeline.run import run
from .conftest import TODAY


def test_end_to_end_offline(registry_path, offline_dir, tmp_path):
    out = tmp_path / "out"
    latest = run(registry=registry_path, out_dir=out, offline_dir=offline_dir, today=TODAY)

    assert (out / "latest.json").exists() and (out / "resorts.json").exists() and (out / "index.html").exists()
    reloaded = json.loads((out / "latest.json").read_text(encoding="utf-8"))
    assert reloaded["today"] == "2026-01-15" and len(reloaded["days"]) == 10
    by_id = {r["id"]: r for r in reloaded["resorts"]}
    assert set(by_id) == {"kuehtai", "sudelfeld"}
    assert all(r["error"] is None for r in by_id.values())

    k = by_id["kuehtai"]
    assert k["micro_region"] == "AT-07-14"
    assert [s["name"] for s in k["stations"]] == ["Kühtai Test"]
    today = k["days"][0]
    assert today["snow"]["hs"] == 112 and today["snow"]["hs_source"] == "station"
    assert today["snow"]["state"] == "fresh_powder"
    assert set(today["snow"]["by_aspect"]) == {"N", "NE", "E", "SE", "S", "SW", "W", "NW"}
    # wind slab on N/NE/E above 2200 m in the fixture bulletin caps those aspects
    assert today["snow"]["by_aspect"]["N"]["capped"] and not today["snow"]["by_aspect"]["S"]["capped"]
    assert today["snow"]["best_aspect"] in ("SE", "S", "SW", "W", "NW")
    assert k["aspect_rose"] is not None and abs(sum(k["aspect_rose"].values()) - 1.0) < 1e-6
    assert k["terrain"]["run_km"] == 40.5
    assert today["avalanche"]["level_top"] == 3 and today["avalanche"]["level_mid"] == 3
    assert today["scores"]["freeride"] > 60
    assert today["blockers"] == {"freeride": [], "piste": []}
    assert k["days"][2]["avalanche"] is None  # bulletin only for the first two days

    s = by_id["sudelfeld"]
    assert s["stations"] == []
    assert s["micro_region"] == "DE-BY-10"
    assert s["days"][0]["avalanche"]["level_top"] == 3  # from the EAWS ratings file
    t = s["days"][0]
    assert t["snow"]["hs_source"] == "model" and t["snow"]["hs"] == 25
    assert any("thin" in b for b in t["blockers"]["piste"])
    assert t["scores"]["piste"] == 0.0
    assert t["snow"]["state"] in ("wet", "hardpack", "crust")

    for r in by_id.values():
        for d in r["days"]:
            for mode in ("freeride", "piste"):
                assert 0 <= d["scores"][mode] <= 100
            assert 0 < d["confidence"] <= 1
    assert reloaded["status"]["sources"]["holidays"]["ok"] == 6
    assert reloaded["status"]["sources"]["bulletins"]["AT-07"][0]["ok"] is True
    assert reloaded["status"]["sources"]["bulletins"]["AT-07"][1]["ok"] is False  # no bulletin for tomorrow


def test_season_gate(registry_path, offline_dir, tmp_path):
    from datetime import date
    from where2ski_pipeline.registry import Resort
    from where2ski_pipeline.run import is_open

    r = Resort(id="x", name="x", region="AT-07", lat=0, lon=0, elevation={"base": 1, "mid": 2, "top": 3})
    assert is_open(r, date(2026, 1, 15)) and not is_open(r, date(2026, 9, 13))
    g = Resort(id="g", name="g", region="AT-07", lat=0, lon=0, elevation={"base": 1, "mid": 2, "top": 3}, glacier=True)
    assert is_open(g, date(2026, 10, 5)) and not is_open(g, date(2026, 9, 13))
    y = Resort(id="y", name="y", region="AT-07", lat=0, lon=0, elevation={"base": 1, "mid": 2, "top": 3},
               season={"open": "01-01", "close": "12-31"})
    assert is_open(y, date(2026, 9, 13))
