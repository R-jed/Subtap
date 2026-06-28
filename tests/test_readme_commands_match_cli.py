"""Phase 27: README commands match CLI."""

from typer.testing import CliRunner

from subtap.cli import app


def test_readme_commands_match_cli():
    """README should document commands that exist in the actual CLI."""
    readme = open("README.md", encoding="utf-8").read()
    runner = CliRunner()

    for command in ("run", "setup", "doctor", "demo", "glossary", "learn", "profile"):
        assert f"subtap {command}" in readme
        assert runner.invoke(app, [command, "--help"]).exit_code == 0

    forbidden = ("第三方 ASR API", "DirectML", "Vulkan")
    for term in forbidden:
        assert term not in readme
