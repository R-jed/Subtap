"""Tests for setup business logic."""

import pytest
from unittest.mock import patch

from subtap.core.setup import SetupWizard


def test_setup_wizard_init():
    """Test SetupWizard initialization."""
    wizard = SetupWizard()
    assert wizard is not None


def test_check_system_deps_ffmpeg_missing():
    """Test system check when ffmpeg is missing."""
    wizard = SetupWizard()
    with patch("shutil.which", return_value=None):
        result = wizard.check_system_deps()
        assert result["ffmpeg"] is False


def test_check_system_deps_ffmpeg_present():
    """Test system check when ffmpeg is present."""
    wizard = SetupWizard()
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        result = wizard.check_system_deps()
        assert result["ffmpeg"] is True


def test_check_system_deps_python_version():
    """Test Python version check."""
    wizard = SetupWizard()
    result = wizard.check_system_deps()
    assert "python" in result
    assert isinstance(result["python"], bool)


def test_check_system_deps_does_not_require_models_dir():
    """setup should not fail before it has a chance to create/download models."""
    wizard = SetupWizard()
    result = wizard.check_system_deps()
    assert "models" not in result


def test_check_config_exists_true(tmp_path):
    """Test config check when config exists."""
    wizard = SetupWizard()
    config_path = tmp_path / ".subtap" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("test: true")

    with patch("subtap.core.setup.Path.home", return_value=tmp_path):
        result = wizard.check_config_exists()
        assert result is True


def test_check_config_exists_false(tmp_path):
    """Test config check when config doesn't exist."""
    wizard = SetupWizard()

    with patch("subtap.core.setup.Path.home", return_value=tmp_path):
        result = wizard.check_config_exists()
        assert result is False


def test_run_init_success():
    """Test successful init."""
    wizard = SetupWizard()

    with patch("subtap.cli.init") as mock_init:
        mock_init.return_value = None
        result = wizard.run_init()
        assert result is True
        mock_init.assert_called_once()


def test_choose_download_source_valid():
    """Test choose_download_source with valid source names."""
    wizard = SetupWizard()
    assert wizard.choose_download_source("hf") == "hf"
    assert wizard.choose_download_source("hf-mirror") == "hf-mirror"
    assert wizard.choose_download_source("modelscope") == "modelscope"
    assert wizard.choose_download_source("manual") == "manual"


def test_choose_download_source_invalid():
    """Test choose_download_source raises ValueError for unknown source."""
    wizard = SetupWizard()
    with pytest.raises(ValueError, match="未知下载方式"):
        wizard.choose_download_source("invalid_source")


def test_run_init_failure():
    """Test failed init."""
    wizard = SetupWizard()

    with patch("subtap.cli.init", side_effect=Exception("Init failed")):
        result = wizard.run_init()
        assert result is False


def test_setup_model_selection_default():
    """Test default downloads asr_0.6b and aligner."""
    from subtap.schemas.config import SubtapConfig

    wizard = SetupWizard()
    with (
        patch.object(wizard, "_download_model") as mock_download,
        patch("subtap.schemas.config.load_config", return_value=SubtapConfig()),
        patch(
            "subtap.core.models.ModelDownloader.check_connectivity", return_value=True
        ),
    ):
        mock_download.return_value = True
        wizard.setup_models(source="hf")
        # Should download asr_0.6b and aligner
        assert mock_download.call_count == 2
        calls = [call.args[1] for call in mock_download.call_args_list]
        assert "aligner" in calls
        assert "asr_0.6b" in calls


def test_setup_model_selection_include_optional():
    """Test include_optional downloads all models."""
    from subtap.schemas.config import SubtapConfig

    wizard = SetupWizard()
    with (
        patch.object(wizard, "_download_model") as mock_download,
        patch("subtap.schemas.config.load_config", return_value=SubtapConfig()),
        patch(
            "subtap.core.models.ModelDownloader.check_connectivity", return_value=True
        ),
    ):
        mock_download.return_value = True
        wizard.setup_models(source="hf", include_optional=True)
        # Should download the three supported 8-bit MLX models.
        assert mock_download.call_count == 3
        calls = [call.args[1] for call in mock_download.call_args_list]
        assert "aligner" in calls
        assert "asr_0.6b" in calls
        assert "asr_1.7b" in calls


def test_setup_include_optional_installs_all_models_when_quality_is_selected():
    """Optional setup keeps the fast ASR available beside the selected quality ASR."""
    from subtap.schemas.config import SubtapConfig

    config = SubtapConfig()
    config.asr.model = "asr_1.7b"
    wizard = SetupWizard()
    with (
        patch.object(wizard, "_download_model", return_value=True) as mock_download,
        patch("subtap.schemas.config.load_config", return_value=config),
        patch(
            "subtap.core.models.ModelDownloader.check_connectivity", return_value=True
        ),
    ):
        wizard.setup_models(source="hf", include_optional=True)

    assert {call.args[1] for call in mock_download.call_args_list} == {
        "asr_0.6b",
        "asr_1.7b",
        "aligner",
    }


def test_setup_model_download_partial_failure():
    """Test setup_models returns False when some downloads fail."""
    wizard = SetupWizard()
    call_count = 0

    def mock_download(downloader, model_name, source="hf"):
        nonlocal call_count
        call_count += 1
        # aligner succeeds, asr fails
        return model_name == "aligner"

    with (
        patch.object(wizard, "_download_model", side_effect=mock_download),
        patch(
            "subtap.core.models.ModelDownloader.check_connectivity", return_value=True
        ),
    ):
        result = wizard.setup_models(source="hf")
        assert result is False
        assert call_count == 2  # aligner + asr_0.6b


def test_setup_model_download_all_fail():
    """Test setup_models returns False when all downloads fail."""
    wizard = SetupWizard()

    with (
        patch.object(wizard, "_download_model", return_value=False),
        patch(
            "subtap.core.models.ModelDownloader.check_connectivity", return_value=True
        ),
    ):
        result = wizard.setup_models(source="hf")
        assert result is False


def test_setup_models_uses_selected_source(monkeypatch, tmp_path):
    """Test setup_models passes source to ModelDownloader.download()."""
    from subtap.core.setup import SetupWizard

    calls = []

    class FakeDownloader:
        def __init__(self, config):
            pass

        def check_connectivity(self, source, repo):
            return True

        def download(self, model_name, source="hf", progress=None):
            calls.append((model_name, source))
            return tmp_path / "models" / model_name

    monkeypatch.setattr("subtap.core.models.ModelDownloader", FakeDownloader)
    monkeypatch.setattr(
        "subtap.schemas.config.load_config",
        lambda path: __import__("subtap.schemas.config").schemas.config.SubtapConfig(),
    )

    ok = SetupWizard().setup_models(source="hf-mirror", include_optional=False)

    assert ok is True
    assert ("asr_0.6b", "hf-mirror") in calls
    assert ("aligner", "hf-mirror") in calls
    assert all(name != "asr_1.7b" for name, _source in calls)


def test_setup_models_fallback_hf_to_mirror(monkeypatch, tmp_path):
    """Test fallback from hf to hf-mirror when hf is unreachable."""
    from subtap.core.setup import SetupWizard

    calls = []

    class FakeDownloader:
        def __init__(self, config):
            pass

        def check_connectivity(self, source, repo):
            return source == "hf-mirror"

        def download(self, model_name, source="hf", progress=None):
            calls.append((model_name, source))
            return tmp_path / "models" / model_name

    monkeypatch.setattr("subtap.core.models.ModelDownloader", FakeDownloader)
    monkeypatch.setattr(
        "subtap.schemas.config.load_config",
        lambda path: __import__("subtap.schemas.config").schemas.config.SubtapConfig(),
    )
    monkeypatch.setattr("typer.prompt", lambda *a, **kw: "y")

    ok = SetupWizard().setup_models(source="ask", include_optional=False)

    assert ok is True
    assert all(source == "hf-mirror" for _, source in calls)


def test_setup_models_fallback_hf_mirror_to_modelscope(monkeypatch, tmp_path):
    """Test fallback chain: hf -> hf-mirror -> modelscope."""
    from subtap.core.setup import SetupWizard

    calls = []

    class FakeDownloader:
        def __init__(self, config):
            pass

        def check_connectivity(self, source, repo):
            return source == "modelscope"

        def download(self, model_name, source="hf", progress=None):
            calls.append((model_name, source))
            return tmp_path / "models" / model_name

    monkeypatch.setattr("subtap.core.models.ModelDownloader", FakeDownloader)
    monkeypatch.setattr(
        "subtap.schemas.config.load_config",
        lambda path: __import__("subtap.schemas.config").schemas.config.SubtapConfig(),
    )
    monkeypatch.setattr("typer.prompt", lambda *a, **kw: "y")

    ok = SetupWizard().setup_models(source="ask", include_optional=False)

    assert ok is True
    assert all(source == "modelscope" for _, source in calls)


def test_setup_models_fallback_all_to_manual(monkeypatch, tmp_path):
    """Test full fallback chain: hf -> hf-mirror -> modelscope -> manual."""
    from subtap.core.setup import SetupWizard

    class FakeDownloader:
        def __init__(self, config):
            pass

        def check_connectivity(self, source, repo):
            return False  # all sources unreachable

        def download(self, model_name, source="hf", progress=None):
            return tmp_path / "models" / model_name

    monkeypatch.setattr("subtap.core.models.ModelDownloader", FakeDownloader)
    monkeypatch.setattr(
        "subtap.schemas.config.load_config",
        lambda path: __import__("subtap.schemas.config").schemas.config.SubtapConfig(),
    )
    monkeypatch.setattr("typer.prompt", lambda *a, **kw: "y")

    wizard = SetupWizard()
    ok = wizard.setup_models(source="ask", include_optional=False)

    # manual prints instructions and returns False
    assert ok is False


def test_setup_models_fallback_user_declines(monkeypatch, tmp_path):
    """Test user declining fallback returns False."""
    from subtap.core.setup import SetupWizard

    class FakeDownloader:
        def __init__(self, config):
            pass

        def check_connectivity(self, source, repo):
            return source != "hf"

        def download(self, model_name, source="hf", progress=None):
            return tmp_path / "models" / model_name

    monkeypatch.setattr("subtap.core.models.ModelDownloader", FakeDownloader)
    monkeypatch.setattr(
        "subtap.schemas.config.load_config",
        lambda path: __import__("subtap.schemas.config").schemas.config.SubtapConfig(),
    )
    monkeypatch.setattr("typer.prompt", lambda *a, **kw: "n")

    ok = SetupWizard().setup_models(source="ask", include_optional=False)

    assert ok is False


def test_fetch_remote_models_openai_compatible(monkeypatch):
    """Test remote model list is fetched from OpenAI-compatible /models."""
    calls = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"id": "agnes-2.0-flash"}, {"id": "other-model"}]}

    class Client:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response()

    monkeypatch.setattr("subtap.core.setup.httpx.Client", Client)

    models = SetupWizard().fetch_remote_models("https://api.example.test/v1", "key")

    assert models == ["agnes-2.0-flash", "other-model"]
    assert calls[0][0] == "https://api.example.test/v1/models"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer key"


def test_configure_remote_api_saves_model_without_key(monkeypatch, tmp_path):
    """Test remote API setup stores URL/model/env name but not raw API key."""
    config_dir = tmp_path / ".subtap"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    config_path.write_text("mode: offline\n", encoding="utf-8")

    wizard = SetupWizard()
    monkeypatch.setattr("subtap.core.setup.Path.home", lambda: tmp_path)
    monkeypatch.setattr(
        wizard,
        "fetch_remote_models",
        lambda base_url, api_key, timeout_sec=60: ["agnes-2.0-flash"],
    )
    monkeypatch.setattr("typer.prompt", lambda *args, **kwargs: "1")

    ok = wizard.configure_remote_api(
        base_url="https://api.example.test/v1",
        api_key="test-api-key",
        api_key_env="SUBTAP_API_KEY",
    )

    text = config_path.read_text(encoding="utf-8")
    assert ok is True
    assert "agnes-2.0-flash" in text
    assert "https://api.example.test/v1" in text
    assert "SUBTAP_API_KEY" in text
    assert "test-api-key" not in text
