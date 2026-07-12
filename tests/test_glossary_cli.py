"""Tests for glossary CLI commands."""

from __future__ import annotations

from typer.testing import CliRunner

from subtap.cli import app
from subtap.schemas.glossary import load_glossary

runner = CliRunner()


def test_default_glossary_path_uses_canonical_directory(tmp_path, monkeypatch):
    from subtap.glossary.cli import _default_path

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert _default_path() == tmp_path / ".subtap" / "glossaries" / "default.yaml"


def test_glossary_command_exists():
    """subtap glossary should expose add, list and import commands."""
    result = runner.invoke(app, ["glossary", "--help"])

    assert result.exit_code == 0
    assert "add" in result.output
    assert "list" in result.output
    assert "import" in result.output


def test_glossary_add_writes_replacement(tmp_path):
    """glossary add should write a replacement rule to YAML."""
    path = tmp_path / "glossary.yaml"

    result = runner.invoke(
        app,
        ["glossary", "add", "--input", "错词=正确词", "--file", str(path)],
    )

    assert result.exit_code == 0
    glossary = load_glossary(path)
    assert glossary.replacements[0].find == "错词"
    assert glossary.replacements[0].replace == "正确词"


def test_glossary_list_reads_file(tmp_path):
    """glossary list should show replacement rules from YAML."""
    path = tmp_path / "glossary.yaml"
    path.write_text(
        """
replacements:
  - find: 错词
    replace: 正确词
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["glossary", "list", "--file", str(path)])

    assert result.exit_code == 0
    assert "错词 -> 正确词" in result.output


def test_glossary_batch_add_from_inline_pairs(tmp_path):
    """batch-add should parse haoone-style inline hotword pairs."""
    path = tmp_path / "glossary.yaml"

    result = runner.invoke(
        app,
        [
            "glossary",
            "batch-add",
            "--language",
            "zh",
            "--input",
            "OpenAI=欧喷AI,Open A I\nChatGPT=chat g p t",
            "--file",
            str(path),
        ],
    )

    assert result.exit_code == 0
    glossary = load_glossary(path)
    assert [(r.find, r.replace) for r in glossary.replacements] == [
        ("欧喷AI", "OpenAI"),
        ("Open A I", "OpenAI"),
        ("chat g p t", "ChatGPT"),
    ]
    assert "已添加 3 条" in result.output


def test_glossary_batch_add_from_block_file(tmp_path):
    """batch-add should parse block format from file."""
    path = tmp_path / "glossary.yaml"
    source = tmp_path / "hotwords.txt"
    source.write_text(
        "OpenAI\n欧喷AI\nOpen A I\n\nChatGPT\nchat g p t\n", encoding="utf-8"
    )

    result = runner.invoke(
        app,
        [
            "glossary",
            "batch-add",
            "--language",
            "zh",
            "--source",
            str(source),
            "--file",
            str(path),
        ],
    )

    assert result.exit_code == 0
    glossary = load_glossary(path)
    assert [(r.find, r.replace) for r in glossary.replacements] == [
        ("欧喷AI", "OpenAI"),
        ("Open A I", "OpenAI"),
        ("chat g p t", "ChatGPT"),
    ]
