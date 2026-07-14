"""Task 2: Doctor 只校验当前运行所需模型."""

from __future__ import annotations

import json
from types import SimpleNamespace

from typer.testing import CliRunner

from subtap.cli import app
from subtap.core.manifest import get_manifest_path, load_manifest
from subtap.core.models import MODEL_REGISTRY
from subtap.schemas.config import SubtapConfig

runner = CliRunner()


def make_config(asr_model: str, aligner_model: str, tmp_path) -> SimpleNamespace:
    """Return a minimal SubtapConfig mock for doctor tests.

    Uses an absolute models.root so _get_model_root does not fall through to
    the module-level DEFAULT_MODEL_ROOT (which is evaluated at import time).
    """
    return SimpleNamespace(
        asr=SimpleNamespace(
            model=asr_model,
            quantization="q8",
            keep_model_alive=False,
            warmup=False,
            hotwords=[],
        ),
        align=SimpleNamespace(
            model=aligner_model,
            quantization="q8",
            keep_model_alive=False,
            warmup=False,
            language="Chinese",
            time_offset_sec=-0.15,
        ),
        remote_api=SimpleNamespace(api_key_env="SUBTAP_API_KEY"),
        models=SimpleNamespace(root=str(tmp_path / ".subtap" / "models")),
    )


def install_model(tmp_path, model_name: str) -> None:
    """Create required_files for a model under tmp_path/.subtap/models/<subdir>/."""
    info = MODEL_REGISTRY[model_name]
    model_dir = tmp_path / ".subtap" / "models" / info["subdir"]
    model_dir.mkdir(parents=True, exist_ok=True)
    entry = load_manifest(get_manifest_path(SubtapConfig())).models[model_name]
    for file in entry.required_files:
        with (model_dir / file.name).open("wb") as handle:
            handle.truncate(file.size_bytes)


def configure_complete_release_environment(monkeypatch, tmp_path):
    """Set up a complete release doctor environment with all dependencies satisfied."""
    config = make_config(
        asr_model="asr_1.7b", aligner_model="aligner", tmp_path=tmp_path
    )
    install_model(tmp_path, "asr_1.7b")
    install_model(tmp_path, "aligner")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr("subtap.schemas.config.load_config", lambda _: config)
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/tool")

    subtap_dir = tmp_path / ".subtap"
    subtap_dir.mkdir(exist_ok=True)
    (subtap_dir / "config.yaml").write_text("mode: offline\n", encoding="utf-8")


def test_release_doctor_ignores_unselected_optional_asr(monkeypatch, tmp_path):
    """asr_0.6b is not selected → required=False, missing does not fail."""
    config = make_config(
        asr_model="asr_1.7b", aligner_model="aligner", tmp_path=tmp_path
    )
    install_model(tmp_path, "asr_1.7b")
    install_model(tmp_path, "aligner")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr("subtap.schemas.config.load_config", lambda _: config)
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/tool")

    subtap_dir = tmp_path / ".subtap"
    subtap_dir.mkdir(exist_ok=True)
    (subtap_dir / "config.yaml").write_text("mode: offline\n", encoding="utf-8")

    result = runner.invoke(app, ["doctor", "--release", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    optional = next(m for m in payload["models"] if m["name"] == "asr_0.6b")
    assert optional["required"] is False
    assert optional["installed"] is False


def test_release_doctor_fails_when_selected_model_is_missing(monkeypatch, tmp_path):
    """asr_1.7b is selected but missing → required=True, exit_code=1."""
    config = make_config(
        asr_model="asr_1.7b", aligner_model="aligner", tmp_path=tmp_path
    )
    install_model(tmp_path, "aligner")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr("subtap.schemas.config.load_config", lambda _: config)
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/tool")

    subtap_dir = tmp_path / ".subtap"
    subtap_dir.mkdir(exist_ok=True)
    (subtap_dir / "config.yaml").write_text("mode: offline\n", encoding="utf-8")

    result = runner.invoke(app, ["doctor", "--release", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    selected = next(m for m in payload["models"] if m["name"] == "asr_1.7b")
    assert selected["required"] is True
    assert selected["installed"] is False


def test_doctor_combines_release_and_workspace_json(monkeypatch, tmp_path):
    """--release --workspace --json outputs single JSON with both release and workspace data."""
    configure_complete_release_environment(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["doctor", "--release", "--workspace", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["release"] is True
    assert "workspace_status" in payload
    assert "checks" in payload
    assert "models" in payload


def test_release_doctor_fails_when_model_status_cannot_be_checked(monkeypatch):
    """ModelRegistry.status raises → release mode must fail."""
    monkeypatch.setattr(
        "subtap.core.models.ModelRegistry.status",
        lambda _self: (_ for _ in ()).throw(RuntimeError("registry unavailable")),
    )
    result = runner.invoke(app, ["doctor", "--release", "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["models_error"] == "registry unavailable"
