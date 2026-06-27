"""Tests for glossary CLI commands."""

from __future__ import annotations

from typer.testing import CliRunner

from subtap.cli import app

runner = CliRunner()


def test_glossary_command_exists():
    """subtap glossary should expose add, list and import commands."""
    result = runner.invoke(app, ["glossary", "--help"])

    assert result.exit_code == 0
    assert "add" in result.output
    assert "list" in result.output
    assert "import" in result.output
