"""Phase 22: doctor model panel."""

from __future__ import annotations

import json
from types import SimpleNamespace

from typer.testing import CliRunner

from subtap.cli import app


def test_doctor_json_reports_models_quantization_and_residency(monkeypatch, tmp_path):
    """doctor --json should show local model and no-residency runtime config."""
    config = SimpleNamespace(
        asr=SimpleNamespace(
            model="asr_0.6b",
            quantization="q8",
            keep_model_alive=False,
            warmup=False,
        ),
        align=SimpleNamespace(
            model="aligner",
            quantization="q8",
            keep_model_alive=False,
            warmup=False,
        ),
    )
    monkeypatch.setattr("subtap.schemas.config.load_config", lambda _path: config)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/tool")

    subtap_dir = tmp_path / ".subtap"
    subtap_dir.mkdir()
    (subtap_dir / "config.yaml").write_text("mode: offline\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["doctor", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["runtime"]["asr_model"] == "asr_0.6b"
    assert payload["runtime"]["asr_quantization"] == "q8"
    assert payload["runtime"]["aligner_model"] == "aligner"
    assert payload["runtime"]["aligner_quantization"] == "q8"
    assert payload["runtime"]["keep_model_alive"] is False
    assert payload["runtime"]["warmup"] is False
