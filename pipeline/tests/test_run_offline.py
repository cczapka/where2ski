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
    assert today["avalanche"]["level_top"] == 3 and today["avalanche"]["level_mid"] == 3
    assert today["scores"]["freeride"] > 60
    assert today["blockers"] == {"freeride": [], "piste": []}
    assert k["days"][2]["avalanche"] is None  # bulletin only for the first two days

    s = by_id["sudelfeld"]
    assert s["stations"] == []
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
