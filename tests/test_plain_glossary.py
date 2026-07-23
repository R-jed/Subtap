from __future__ import annotations

import json
from pathlib import Path

import pytest

from subtap.core.pipeline import Pipeline
from subtap.core.user_resources import ensure_default_glossary, ensure_learned_glossary
from subtap.schemas.config import SubtapConfig
from subtap.schemas.glossary import (
    GlossaryTerm,
    load_glossary,
    remove_plain_glossary_entry,
    upsert_plain_glossary_terms,
)


def test_plain_glossary_accepts_textedit_friendly_syntax(tmp_path: Path) -> None:
    path = tmp_path / "default.txt"
    path.write_text(
        "\ufeff# 我的热词\r\nSubtap\r\n理光GR4 ＝ 李光机亚四，吉亚四\r\n",
        encoding="utf-8",
    )

    glossary = load_glossary(path)

    assert [(term.canonical, term.aliases) for term in glossary.terms] == [
        ("Subtap", []),
        ("理光GR4", ["李光机亚四", "吉亚四"]),
    ]


def test_plain_glossary_rejects_whole_file_with_all_related_lines(
    tmp_path: Path,
) -> None:
    path = tmp_path / "default.txt"
    path.write_text(
        "Subtap\n"
        "Subtap = 苏塔普\n"
        "OpenAI = 开放AI\n"
        "ChatGPT = 开放AI\n"
        "坏行 = \n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc_info:
        load_glossary(path)

    message = str(exc_info.value)
    assert "第 1 行" in message
    assert "第 2 行" in message
    assert "第 3 行" in message
    assert "第 4 行" in message
    assert "第 5 行" in message


def test_non_object_yaml_is_not_silently_treated_as_a_hotword(tmp_path: Path) -> None:
    path = tmp_path / "glossary.yaml"
    path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="根节点必须是 YAML 对象"):
        load_glossary(path)


def test_plain_glossary_commands_preserve_comments_blank_lines_and_order(
    tmp_path: Path,
) -> None:
    path = tmp_path / "default.txt"
    path.write_text(
        "# 相机\n" "理光GR4 = 李光机亚四\n" "\n" "# 产品\n" "Subtap\n",
        encoding="utf-8",
    )

    upsert_plain_glossary_terms(
        path,
        [GlossaryTerm(canonical="理光GR4", aliases=["吉亚四"])],
    )
    upsert_plain_glossary_terms(
        path,
        [GlossaryTerm(canonical="OpenAI", aliases=["开放AI"])],
    )

    assert path.read_text(encoding="utf-8") == (
        "# 相机\n"
        "理光GR4 = 李光机亚四, 吉亚四\n"
        "\n"
        "# 产品\n"
        "Subtap\n"
        "OpenAI = 开放AI\n"
    )

    assert remove_plain_glossary_entry(path, "吉亚四") is True
    assert path.read_text(encoding="utf-8") == (
        "# 相机\n" "\n" "# 产品\n" "Subtap\n" "OpenAI = 开放AI\n"
    )


def test_default_yaml_migrates_losslessly_then_keeps_backup(tmp_path: Path) -> None:
    old = tmp_path / "glossaries" / "default.yaml"
    old.parent.mkdir(parents=True)
    old.write_text(
        "terms:\n"
        "  - canonical: 理光GR4\n"
        "    aliases: [李光机亚四, 吉亚四]\n"
        "replacements: []\n"
        "style: []\n",
        encoding="utf-8",
    )

    result = ensure_default_glossary(tmp_path)

    assert result == old.with_name("default.txt")
    assert load_glossary(result) == load_glossary(old.with_name("default.yaml.bak"))
    assert not old.exists()


def test_default_yaml_migration_rejects_unrepresentable_sections(
    tmp_path: Path,
) -> None:
    old = tmp_path / "glossaries" / "default.yaml"
    old.parent.mkdir(parents=True)
    original = "terms: []\nstyle:\n  - 保持正式语气\n"
    old.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="无法无损迁移"):
        ensure_default_glossary(tmp_path)

    assert old.read_text(encoding="utf-8") == original
    assert not old.with_name("default.txt").exists()
    assert not old.with_name("default.yaml.bak").exists()


def test_learned_yaml_migrates_before_the_system_appends(tmp_path: Path) -> None:
    old = tmp_path / "glossaries" / "learned.yaml"
    old.parent.mkdir(parents=True)
    old.write_text("VITURE=维图尔\n", encoding="utf-8")

    result = ensure_learned_glossary(tmp_path)

    assert result == old.with_name("learned.txt")
    assert load_glossary(result).resolve_alias("维图尔") == "VITURE"
    assert old.with_name("learned.yaml.bak").is_file()


def test_learning_never_writes_selected_or_default_glossary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    selected = tmp_path / "selected.txt"
    original = "# 用户文件\nSubtap\n"
    selected.write_text(original, encoding="utf-8")
    pipeline = Pipeline(SubtapConfig(), work_dir=tmp_path / "work")
    ops_path = pipeline.workspace.root / "llm_hotword_ops.jsonl"
    ops_path.parent.mkdir(parents=True)
    ops_path.write_text(
        json.dumps({"from": "TEST", "to": "测试词", "segment_id": 0}) + "\n",
        encoding="utf-8",
    )

    result = pipeline.run_stage("learn", glossary_path=selected)

    learned = tmp_path / ".subtap" / "glossaries" / "learned.txt"
    assert result["path"] == str(learned)
    assert learned.is_file()
    assert selected.read_text(encoding="utf-8") == original
    assert not (tmp_path / ".subtap" / "glossaries" / "default.txt").exists()
