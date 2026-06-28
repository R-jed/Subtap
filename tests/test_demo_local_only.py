"""Phase 27: demo defaults."""

from typer.testing import CliRunner

from subtap.cli import app


def test_demo_local_only_help():
    """Demo help should state it runs locally by default."""
    result = CliRunner().invoke(app, ["demo", "--help"])

    assert result.exit_code == 0
    assert "默认本地" in result.output
    assert "final.srt" in result.output
