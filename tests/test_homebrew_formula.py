"""Tests for Homebrew Formula template and renderer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
TEMPLATE = ROOT / "packaging/homebrew/subtap.rb.in"
RENDERER = ROOT / "scripts/render_homebrew_formula.py"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_MANIFEST = {
    "target": {"python": "3.13", "platform": "macosx_14_0_arm64"},
    "subtap_version": "0.1.0",
    "external_packages": [
        {"name": "numpy", "requirement": ">=1.26.4", "formula": "numpy"},
        {"name": "scipy", "requirement": ">=1.10.0", "formula": "scipy"},
    ],
    "packages": [
        {
            "name": "subtap",
            "version": "0.1.0",
            "sha256": "111111111111111111111111111111111111111111111111111111111111111a",
            "license": "MIT",
            "filename": "subtap-0.1.0-py3-none-any.whl",
            "size": 1000,
            "tags": ["py3-none-any"],
            "url": "project:.",
            "source_sha256": "111111111111111111111111111111111111111111111111111111111111111a",
        },
        {
            "name": "click",
            "version": "8.1.7",
            "sha256": "222222222222222222222222222222222222222222222222222222222222222b",
            "license": "BSD-3-Clause",
            "filename": "click-8.1.7-py3-none-any.whl",
            "size": 2000,
            "tags": ["py3-none-any"],
            "url": "https://files.pythonhosted.org/click-8.1.7-py3-none-any.whl",
            "source_sha256": "222222222222222222222222222222222222222222222222222222222222222b",
        },
        {
            "name": "sentencepiece",
            "version": "0.2.2",
            "sha256": "333333333333333333333333333333333333333333333333333333333333333c",
            "license": "Apache-2.0",
            "filename": "sentencepiece-0.2.2-cp313-cp313-macosx_11_0_arm64.whl",
            "size": 3000,
            "tags": ["cp313-cp313-macosx_11_0_arm64"],
            "url": "https://example.com/sentencepiece-0.2.2-cp313-cp313-macosx_11_0_arm64.whl",
            "source_sha256": "333333333333333333333333333333333333333333333333333333333333333c",
        },
    ],
}

SAMPLE_WHEELHOUSE_URL = (
    "https://github.com/example/subtap/releases/download/v0.1.0/"
    "subtap-0.1.0-py313-macos-arm64-wheelhouse.tar.gz"
)


@pytest.fixture()
def manifest_path(tmp_path: Path) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(SAMPLE_MANIFEST, indent=2), encoding="utf-8")
    return path


@pytest.fixture()
def template_copy(tmp_path: Path) -> Path:
    dest = tmp_path / "subtap.rb.in"
    dest.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


@pytest.fixture()
def wheelhouse_path(tmp_path: Path) -> Path:
    path = tmp_path / "subtap-wheelhouse.tar.gz"
    path.write_bytes(b"sealed wheelhouse")
    return path


# ---------------------------------------------------------------------------
# Template structure tests
# ---------------------------------------------------------------------------


class TestTemplateStructure:
    """Validate the .rb.in template has required Homebrew Formula elements."""

    def test_template_exists(self) -> None:
        assert TEMPLATE.is_file(), f"Template missing: {TEMPLATE}"

    def test_template_has_no_bottle_block(self) -> None:
        """Formula must not contain a bottle block — Homebrew CI generates it."""
        text = TEMPLATE.read_text(encoding="utf-8")
        assert "bottle do" not in text

    def test_python313_dependency(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        assert 'depends_on "python@3.13"' in text

    def test_numpy_dependency(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        assert 'depends_on "numpy"' in text

    def test_scipy_dependency(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        assert 'depends_on "scipy"' in text

    def test_ffmpeg_dependency(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        assert 'depends_on "ffmpeg"' in text

    def test_pip_no_index(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        assert "--no-index" in text

    def test_pip_no_deps(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        assert "--no-deps" in text

    def test_pip_require_hashes(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        assert "--require-hashes" in text

    def test_pip_only_binary(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        assert "--only-binary=:all:" in text

    def test_pip_uses_locked_requirements_from_local_wheels(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        assert "requirements.txt" in text
        assert "--find-links" in text
        assert ".pip_install [" not in text
        assert 'wheelhouse = buildpath/"wheelhouse"' in text

    def test_formula_explicitly_uses_homebrew_python_packages(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        assert "system_site_packages: true" in text

    def test_formula_rejects_unsupported_platform_before_install(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        assert "OS.mac?" in text
        assert "Hardware::CPU.arm?" in text
        assert "odie" in text

    def test_test_block_exists(self) -> None:
        """Template must contain a test do block."""
        text = TEMPLATE.read_text(encoding="utf-8")
        assert "test do" in text

    def test_test_block_verifies_cli(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        # Should invoke the CLI in the test block
        assert "subtap" in text.split("test do")[1]

    def test_test_block_verifies_doctor(self) -> None:
        """test do must verify `subtap doctor` works."""
        text = TEMPLATE.read_text(encoding="utf-8")
        test_section = text.split("test do")[1]
        assert "doctor" in test_section

    def test_test_block_imports_subtap_module(self) -> None:
        """test do must verify key module imports."""
        text = TEMPLATE.read_text(encoding="utf-8")
        test_section = text.split("test do")[1]
        assert "import subtap" in test_section

    def test_test_block_checks_numpy_source(self) -> None:
        """test do must verify numpy comes from Homebrew, not bundled."""
        text = TEMPLATE.read_text(encoding="utf-8")
        test_section = text.split("test do")[1]
        assert "numpy" in test_section
        assert "Formula" in test_section

    def test_test_block_checks_scipy_source(self) -> None:
        """test do must verify scipy comes from Homebrew, not bundled."""
        text = TEMPLATE.read_text(encoding="utf-8")
        test_section = text.split("test do")[1]
        assert "scipy" in test_section

    def test_test_block_refutes_numpy_in_venv(self) -> None:
        """test do must ensure no duplicate numpy inside venv."""
        text = TEMPLATE.read_text(encoding="utf-8")
        test_section = text.split("test do")[1]
        assert "refute_predicate" in test_section
        assert "numpy" in test_section

    def test_test_block_refutes_scipy_in_venv(self) -> None:
        """test do must ensure no duplicate scipy inside venv."""
        text = TEMPLATE.read_text(encoding="utf-8")
        test_section = text.split("test do")[1]
        assert "refute_predicate" in test_section
        assert "scipy" in test_section

    def test_version_placeholder(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        assert "VERSION_PLACEHOLDER" in text

    def test_wheelhouse_url_placeholder(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        assert "WHEELHOUSE_URL_PLACEHOLDER" in text

    def test_wheelhouse_sha256_placeholder(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        assert "WHEELHOUSE_SHA256_PLACEHOLDER" in text


# ---------------------------------------------------------------------------
# Renderer tests
# ---------------------------------------------------------------------------


def _import_renderer():
    import importlib.util

    spec = importlib.util.spec_from_file_location("render_homebrew_formula", RENDERER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestRenderer:
    """Test render_homebrew_formula.render()."""

    def test_render_produces_valid_ruby(
        self, manifest_path: Path, template_copy: Path, wheelhouse_path: Path
    ) -> None:
        mod = _import_renderer()
        result = mod.render(
            manifest_path=manifest_path,
            template_path=template_copy,
            wheelhouse_url=SAMPLE_WHEELHOUSE_URL,
            wheelhouse_path=wheelhouse_path,
        )
        assert "class Subtap < Formula" in result
        assert "VERSION_PLACEHOLDER" not in result
        assert "WHEELHOUSE_URL_PLACEHOLDER" not in result
        assert "WHEELHOUSE_SHA256_PLACEHOLDER" not in result

    def test_render_injects_version(
        self, manifest_path: Path, template_copy: Path, wheelhouse_path: Path
    ) -> None:
        mod = _import_renderer()
        result = mod.render(
            manifest_path=manifest_path,
            template_path=template_copy,
            wheelhouse_url=SAMPLE_WHEELHOUSE_URL,
            wheelhouse_path=wheelhouse_path,
        )
        assert SAMPLE_MANIFEST["subtap_version"] in result

    def test_render_injects_wheelhouse_url(
        self, manifest_path: Path, template_copy: Path, wheelhouse_path: Path
    ) -> None:
        mod = _import_renderer()
        result = mod.render(
            manifest_path=manifest_path,
            template_path=template_copy,
            wheelhouse_url=SAMPLE_WHEELHOUSE_URL,
            wheelhouse_path=wheelhouse_path,
        )
        assert SAMPLE_WHEELHOUSE_URL in result

    def test_render_injects_wheelhouse_sha256(
        self, manifest_path: Path, template_copy: Path, wheelhouse_path: Path
    ) -> None:
        mod = _import_renderer()
        result = mod.render(
            manifest_path=manifest_path,
            template_path=template_copy,
            wheelhouse_url=SAMPLE_WHEELHOUSE_URL,
            wheelhouse_path=wheelhouse_path,
        )
        assert hashlib.sha256(wheelhouse_path.read_bytes()).hexdigest() in result

    def test_render_preserves_deps(
        self, manifest_path: Path, template_copy: Path, wheelhouse_path: Path
    ) -> None:
        mod = _import_renderer()
        result = mod.render(
            manifest_path=manifest_path,
            template_path=template_copy,
            wheelhouse_url=SAMPLE_WHEELHOUSE_URL,
            wheelhouse_path=wheelhouse_path,
        )
        for dep in ("python@3.13", "numpy", "scipy", "ffmpeg"):
            assert f'depends_on "{dep}"' in result

    def test_render_preserves_pip_flags(
        self, manifest_path: Path, template_copy: Path, wheelhouse_path: Path
    ) -> None:
        mod = _import_renderer()
        result = mod.render(
            manifest_path=manifest_path,
            template_path=template_copy,
            wheelhouse_url=SAMPLE_WHEELHOUSE_URL,
            wheelhouse_path=wheelhouse_path,
        )
        for flag in (
            "--no-index",
            "--no-deps",
            "--require-hashes",
            "--only-binary=:all:",
        ):
            assert flag in result

    def test_render_preserves_test_block(
        self, manifest_path: Path, template_copy: Path, wheelhouse_path: Path
    ) -> None:
        mod = _import_renderer()
        result = mod.render(
            manifest_path=manifest_path,
            template_path=template_copy,
            wheelhouse_url=SAMPLE_WHEELHOUSE_URL,
            wheelhouse_path=wheelhouse_path,
        )
        assert "test do" in result

    def test_render_calculates_sha256_from_the_wheelhouse(
        self,
        manifest_path: Path,
        template_copy: Path,
        wheelhouse_path: Path,
    ) -> None:
        mod = _import_renderer()
        result = mod.render(
            manifest_path=manifest_path,
            template_path=template_copy,
            wheelhouse_url=SAMPLE_WHEELHOUSE_URL,
            wheelhouse_path=wheelhouse_path,
        )

        assert hashlib.sha256(wheelhouse_path.read_bytes()).hexdigest() in result


class TestRendererValidation:
    """Renderer must fail fast on inconsistent data."""

    def test_rejects_missing_manifest(
        self, template_copy: Path, wheelhouse_path: Path
    ) -> None:
        mod = _import_renderer()
        with pytest.raises(ValueError, match="cannot read"):
            mod.render(
                manifest_path=Path("/nonexistent/manifest.json"),
                template_path=template_copy,
                wheelhouse_url=SAMPLE_WHEELHOUSE_URL,
                wheelhouse_path=wheelhouse_path,
            )

    def test_rejects_missing_template(
        self, manifest_path: Path, wheelhouse_path: Path
    ) -> None:
        mod = _import_renderer()
        with pytest.raises(ValueError, match="cannot read"):
            mod.render(
                manifest_path=manifest_path,
                template_path=Path("/nonexistent/subtap.rb.in"),
                wheelhouse_url=SAMPLE_WHEELHOUSE_URL,
                wheelhouse_path=wheelhouse_path,
            )

    def test_rejects_empty_wheelhouse_url(
        self, manifest_path: Path, template_copy: Path, wheelhouse_path: Path
    ) -> None:
        mod = _import_renderer()
        with pytest.raises(ValueError):
            mod.render(
                manifest_path=manifest_path,
                template_path=template_copy,
                wheelhouse_url="",
                wheelhouse_path=wheelhouse_path,
            )

    def test_rejects_missing_wheelhouse(
        self, manifest_path: Path, template_copy: Path
    ) -> None:
        mod = _import_renderer()
        with pytest.raises(ValueError, match="cannot read wheelhouse"):
            mod.render(
                manifest_path=manifest_path,
                template_path=template_copy,
                wheelhouse_url=SAMPLE_WHEELHOUSE_URL,
                wheelhouse_path=Path("/nonexistent/wheelhouse.tar.gz"),
            )

    def test_rejects_malformed_manifest(
        self, tmp_path: Path, template_copy: Path, wheelhouse_path: Path
    ) -> None:
        bad = tmp_path / "manifest.json"
        bad.write_text("not json", encoding="utf-8")
        mod = _import_renderer()
        with pytest.raises(ValueError, match="invalid JSON"):
            mod.render(
                manifest_path=bad,
                template_path=template_copy,
                wheelhouse_url=SAMPLE_WHEELHOUSE_URL,
                wheelhouse_path=wheelhouse_path,
            )

    def test_accepts_wheelhouse_without_manifest_sha256(
        self, manifest_path: Path, template_copy: Path, wheelhouse_path: Path
    ) -> None:
        """The Formula SHA comes from the immutable archive, not its contents."""
        mod = _import_renderer()
        result = mod.render(
            manifest_path=manifest_path,
            template_path=template_copy,
            wheelhouse_url=SAMPLE_WHEELHOUSE_URL,
            wheelhouse_path=wheelhouse_path,
        )
        assert "class Subtap < Formula" in result

    def test_rejects_missing_subtap_version(
        self, tmp_path: Path, template_copy: Path, wheelhouse_path: Path
    ) -> None:
        """Render fails fast when manifest lacks subtap_version."""
        manifest_no_version: dict[str, object] = {
            "packages": [],
        }
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps(manifest_no_version, indent=2), encoding="utf-8")
        mod = _import_renderer()
        with pytest.raises(ValueError, match="subtap_version"):
            mod.render(
                manifest_path=path,
                template_path=template_copy,
                wheelhouse_url=SAMPLE_WHEELHOUSE_URL,
                wheelhouse_path=wheelhouse_path,
            )

    def test_rejects_empty_subtap_version(
        self, tmp_path: Path, template_copy: Path, wheelhouse_path: Path
    ) -> None:
        """Render fails fast when manifest has empty subtap_version."""
        manifest_empty_version = {
            "subtap_version": "",
            "packages": [],
        }
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps(manifest_empty_version, indent=2), encoding="utf-8")
        mod = _import_renderer()
        with pytest.raises(ValueError, match="subtap_version"):
            mod.render(
                manifest_path=path,
                template_path=template_copy,
                wheelhouse_url=SAMPLE_WHEELHOUSE_URL,
                wheelhouse_path=wheelhouse_path,
            )
