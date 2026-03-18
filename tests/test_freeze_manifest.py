import json

import backtest.train as train_mod


def test_freeze_params_updates_manifest(tmp_path, monkeypatch):
    art_dir = tmp_path / "artifacts"
    frozen_dir = art_dir / "frozen_params"
    report_dir = art_dir / "reports"
    manifest_file = frozen_dir / "MANIFEST.json"

    monkeypatch.setattr(train_mod, "ART_DIR", str(art_dir))
    monkeypatch.setattr(train_mod, "FROZEN_DIR", str(frozen_dir))
    monkeypatch.setattr(train_mod, "REPORT_DIR", str(report_dir))
    monkeypatch.setattr(train_mod, "MANIFEST_FILE", str(manifest_file))

    spec = train_mod.TrainSpec(symbols=["AAPL"], start="2020-01-01", end="2020-12-31")
    frozen_path = train_mod.freeze_params("trend", {"breakout_window": 20}, spec, {"sharpe": 1.2})

    with open(frozen_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    with open(manifest_file, "r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    assert payload["strategy"] == "trend"
    assert "trend" in manifest["strategies"]
    assert manifest["strategies"]["trend"]["file"].endswith("trend.json")
