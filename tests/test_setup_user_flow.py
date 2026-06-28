"""Phase 27: setup user flow."""

from subtap.core.setup import SetupWizard


def test_setup_user_flow_checks_user_visible_requirements(monkeypatch, tmp_path):
    """Setup should check FFmpeg, Python, MLX, models, and output directory."""
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/tool")
    monkeypatch.setattr("importlib.util.find_spec", lambda _name: object())
    monkeypatch.chdir(tmp_path)

    deps = SetupWizard().check_system_deps()

    for key in ("ffmpeg", "ffprobe", "python", "mlx", "models", "output"):
        assert key in deps
    assert "warmup" not in deps
    assert "keep_model_alive" not in deps
