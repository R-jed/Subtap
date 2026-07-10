"""Tests for hotword glossary management."""

from __future__ import annotations

from pathlib import Path

import pytest

from subtap.glossary.hotword import (
    Hotword,
    HotwordGlossary,
    load_glossary,
    save_glossary,
)


class TestHotword:
    """Test Hotword dataclass."""

    def test_basic_hotword(self):
        hw = Hotword(word="达芬奇", aliases=["达文西", "大芬奇"])
        assert hw.word == "达芬奇"
        assert hw.aliases == ["达文西", "大芬奇"]


class TestHotwordGlossary:
    """Test HotwordGlossary class."""

    def test_empty_glossary(self):
        glossary = HotwordGlossary(lang="zh")
        assert glossary.lang == "zh"
        assert len(glossary.hotwords) == 0

    def test_add_hotword(self):
        glossary = HotwordGlossary(lang="zh")
        glossary.add(Hotword(word="达芬奇", aliases=["达文西"]))
        assert len(glossary.hotwords) == 1
        assert glossary.hotwords[0].word == "达芬奇"

    def test_add_alias(self):
        glossary = HotwordGlossary(lang="zh")
        glossary.add_alias("达芬奇", "达文西")
        glossary.add_alias("达芬奇", "大芬奇")
        assert len(glossary.hotwords) == 1
        assert glossary.hotwords[0].aliases == ["达文西", "大芬奇"]

    def test_add_alias_duplicate(self):
        glossary = HotwordGlossary(lang="zh")
        glossary.add_alias("达芬奇", "达文西")
        glossary.add_alias("达芬奇", "达文西")  # duplicate
        assert len(glossary.hotwords) == 1
        assert glossary.hotwords[0].aliases == ["达文西"]

    def test_find_by_alias(self):
        glossary = HotwordGlossary(lang="zh")
        glossary.add(Hotword(word="达芬奇", aliases=["达文西", "大芬奇"]))
        result = glossary.find_by_alias("达文西")
        assert result is not None
        assert result.word == "达芬奇"

    def test_find_by_alias_not_found(self):
        glossary = HotwordGlossary(lang="zh")
        glossary.add(Hotword(word="达芬奇", aliases=["达文西"]))
        result = glossary.find_by_alias("苹果")
        assert result is None

    def test_remove_hotword(self):
        glossary = HotwordGlossary(lang="zh")
        glossary.add(Hotword(word="达芬奇", aliases=["达文西"]))
        glossary.remove("达芬奇")
        assert len(glossary.hotwords) == 0


class TestLoadSaveGlossary:
    """Test load and save functions."""

    def test_save_and_load(self, tmp_path):
        path = tmp_path / "hotwords_zh.tsv"
        glossary = HotwordGlossary(lang="zh")
        glossary.add_alias("达芬奇", "达文西")
        glossary.add_alias("达芬奇", "大芬奇")
        glossary.add_alias("浩瀚", "浩瀚")
        save_glossary(glossary, path)

        loaded = load_glossary(path, lang="zh")
        assert len(loaded.hotwords) == 2
        assert loaded.hotwords[0].word == "达芬奇"
        assert loaded.hotwords[0].aliases == ["达文西", "大芬奇"]
        assert loaded.hotwords[1].word == "浩瀚"

    def test_load_nonexistent(self, tmp_path):
        path = tmp_path / "nonexistent.tsv"
        glossary = load_glossary(path, lang="zh")
        assert len(glossary.hotwords) == 0

    def test_load_format(self, tmp_path):
        """Test loading the equals format."""
        path = tmp_path / "hotwords_zh.txt"
        path.write_text(
            "达芬奇=达文西,大芬奇\nGR=吉亚斯,吉奥,吉亚\n",
            encoding="utf-8",
        )
        loaded = load_glossary(path, lang="zh")
        assert len(loaded.hotwords) == 2
        assert loaded.hotwords[0].word == "达芬奇"
        assert loaded.hotwords[0].aliases == ["达文西", "大芬奇"]
        assert loaded.hotwords[1].word == "GR"
        assert loaded.hotwords[1].aliases == ["吉亚斯", "吉奥", "吉亚"]

    def test_save_format(self, tmp_path):
        """Test saving in equals format."""
        path = tmp_path / "hotwords_zh.txt"
        glossary = HotwordGlossary(lang="zh")
        glossary.add_alias("达芬奇", "达文西")
        glossary.add_alias("达芬奇", "大芬奇")
        save_glossary(glossary, path)

        content = path.read_text(encoding="utf-8")
        assert content == "达芬奇=达文西,大芬奇\n"

    def test_load_encoding_error_returns_empty(self, tmp_path, caplog):
        """UnicodeDecodeError should log warning and return empty glossary."""
        path = tmp_path / "bad_encoding.txt"
        path.write_bytes(b"\xff\xfe\x00\x01invalid utf-8 content")

        import logging

        with caplog.at_level(logging.WARNING):
            glossary = load_glossary(path, lang="zh")

        assert len(glossary.hotwords) == 0
        assert "Failed to decode glossary" in caplog.text

    def test_load_permission_error_propagates(self, tmp_path, monkeypatch):
        """PermissionError (non-recoverable) should propagate, not be swallowed."""
        path = tmp_path / "glossary.txt"
        path.write_text("达芬奇=达文西\n", encoding="utf-8")

        def raise_permission_error(*args, **kwargs):
            raise PermissionError("Permission denied")

        monkeypatch.setattr("pathlib.Path.read_text", raise_permission_error)

        with pytest.raises(PermissionError, match="Permission denied"):
            load_glossary(path, lang="zh")
