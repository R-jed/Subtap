"""Phase 27: doctor panel."""

import json
from types import SimpleNamespace

from typer.testing import CliRunner

from subtap.cli import app


def test_doctor_panel_reports_runtime_privacy_and_output(monkeypatch, tmp_path):
    """doctor --json should expose local-first runtime, output, and privacy state."""
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
        remote_api=SimpleNamespace(api_key_env="SUBTAP_API_KEY"),
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
    assert payload["runtime"]["device_backend"] == "mlx-metal"
    assert payload["privacy"]["external_audio_sent"] is False
    assert payload["privacy"]["local_only_available"] is True
    assert payload["output"]["default_dir"] == "./output"
    assert payload["llm"]["api_configured"] is False


def test_doctor_panel_reports_remote_asr_audio_risk(monkeypatch, tmp_path):
    """doctor --json should not claim local audio privacy for remote ASR."""
    config = SimpleNamespace(
        asr=SimpleNamespace(
            backend="http-asr",
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
        remote_api=SimpleNamespace(api_key_env="SUBTAP_API_KEY"),
    )
    monkeypatch.setattr("subtap.schemas.config.load_config", lambda _path: config)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/tool")

    subtap_dir = tmp_path / ".subtap"
    subtap_dir.mkdir()
    (subtap_dir / "config.yaml").write_text("mode: online\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["doctor", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["privacy"]["external_audio_sent"] is True
