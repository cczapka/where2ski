import json

import pytest

from where2ski_pipeline.http import Http, RecordedError
from where2ski_pipeline.run import RUN_META, run
from .conftest import TODAY


def _strip(latest):
    return json.dumps(latest, sort_keys=True)


def test_recorded_run_replays_identically(registry_path, offline_dir, tmp_path):
    rec = tmp_path / "rec"
    first = run(registry=registry_path, out_dir=tmp_path / "a", offline_dir=offline_dir, today=TODAY, record_dir=rec)
    meta = json.loads((rec / RUN_META).read_text())
    assert meta["today"] == TODAY.isoformat()
    # replay without --today: date and run time come from the recording
    second = run(registry=registry_path, out_dir=tmp_path / "b", offline_dir=rec)
    assert _strip(first) == _strip(second)


def test_recorded_failure_is_replayed(tmp_path):
    (tmp_path / "x.json.error").write_text("429 Client Error")
    http = Http(offline_dir=tmp_path)
    with pytest.raises(RecordedError, match="429"):
        http.get_text("https://example.invalid", key="x.json")
