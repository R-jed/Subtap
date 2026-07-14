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


def test_glossary_add_writes_canonical_term(tmp_path):
    """glossary add should store canonical terms and aliases in YAML."""
    path = tmp_path / "glossary.yaml"

    result = runner.invoke(
        app,
        ["glossary", "add", "--input", "正确词=错词", "--file", str(path)],
    )

    assert result.exit_code == 0
    glossary = load_glossary(path)
    assert glossary.terms[0].canonical == "正确词"
    assert glossary.terms[0].aliases == ["错词"]


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
    assert [(term.canonical, term.aliases) for term in glossary.terms] == [
        ("OpenAI", ["欧喷AI", "Open A I"]),
        ("ChatGPT", ["chat g p t"]),
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
    assert [(term.canonical, term.aliases) for term in glossary.terms] == [
        ("OpenAI", ["欧喷AI", "Open A I"]),
        ("ChatGPT", ["chat g p t"]),
    ]


def test_glossary_commands_preserve_each_others_hotwords(tmp_path, monkeypatch):
    """Both public glossary command groups must share one lossless store."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    path = tmp_path / ".subtap" / "glossaries" / "default.yaml"

    first = runner.invoke(
        app,
        ["glossary", "hotword", "add", "理光GR4", "吉亚四"],
    )
    second = runner.invoke(
        app,
        [
            "glossary",
            "add",
            "--input",
            "理光GR3=吉亚三",
            "--file",
            str(path),
        ],
    )
    hotword_list = runner.invoke(app, ["glossary", "hotword", "list"])
    glossary_list = runner.invoke(
        app,
        ["glossary", "list", "--file", str(path)],
    )

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert hotword_list.exit_code == 0
    assert glossary_list.exit_code == 0
    assert "理光GR4" in hotword_list.output
    assert "理光GR3" in hotword_list.output
    assert "理光GR4" in glossary_list.output
    assert "理光GR3" in glossary_list.output


def test_glossary_commands_merge_aliases_for_the_same_term(tmp_path, monkeypatch):
    """Both command groups must upsert one canonical term instead of duplicating it."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    path = tmp_path / ".subtap" / "glossaries" / "default.yaml"

    first = runner.invoke(
        app,
        [
            "glossary",
            "add",
            "--input",
            "理光GR4=吉亚四",
            "--file",
            str(path),
        ],
    )
    second = runner.invoke(
        app,
        ["glossary", "hotword", "add", "理光GR4", "李光GR4"],
    )

    assert first.exit_code == 0
    assert second.exit_code == 0
    glossary = load_glossary(path)
    assert [(term.canonical, term.aliases) for term in glossary.terms] == [
        ("理光GR4", ["吉亚四", "李光GR4"]),
    ]


def test_hotword_command_preserves_canonical_glossary_metadata(tmp_path, monkeypatch):
    """Adding a hotword must not downgrade or discard the YAML document."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    path = tmp_path / ".subtap" / "glossaries" / "default.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        """terms:
- canonical: 理光GR3
  aliases: [吉亚三]
replacements:
- find: 防低键
  replace: 防滴溅
style:
- 保留产品型号大小写
""",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["glossary", "hotword", "add", "理光GR4", "吉亚四"],
    )

    assert result.exit_code == 0
    glossary = load_glossary(path)
    assert [(term.canonical, term.aliases) for term in glossary.terms] == [
        ("理光GR3", ["吉亚三"]),
        ("理光GR4", ["吉亚四"]),
    ]
    assert [(item.find, item.replace) for item in glossary.replacements] == [
        ("防低键", "防滴溅")
    ]
    assert glossary.style == ["保留产品型号大小写"]


def test_batch_added_terms_are_visible_to_hotword_command(tmp_path, monkeypatch):
    """Batch and interactive commands must expose the same hotword entries."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    path = tmp_path / ".subtap" / "glossaries" / "default.yaml"

    added = runner.invoke(
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
    listed = runner.invoke(app, ["glossary", "hotword", "list"])

    assert added.exit_code == 0
    assert listed.exit_code == 0
    assert "OpenAI" in listed.output
    assert "ChatGPT" in listed.output


def test_batch_add_rejects_invalid_entries_without_writing(tmp_path):
    """One malformed entry must reject the whole batch instead of being discarded."""
    path = tmp_path / "glossary.yaml"

    result = runner.invoke(
        app,
        [
            "glossary",
            "batch-add",
            "--language",
            "zh",
            "--input",
            "OpenAI=欧喷AI\n坏记录=",
            "--file",
            str(path),
        ],
    )

    assert result.exit_code == 1
    assert "术语和别名不能为空" in result.output
    assert not path.exists()
