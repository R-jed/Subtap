"""Tests for hotword replacement — now using HotwordGlossary directly."""

from __future__ import annotations

from pathlib import Path

import pytest

from subtap.glossary.hotword import Hotword, HotwordGlossary, load_glossary


class TestReplaceInText:
    """Test text replacement via HotwordGlossary.replace_in_text."""

    def test_single_hotword(self):
        glossary = HotwordGlossary(lang="zh")
        glossary.add(Hotword(word="达芬奇", aliases=["达文西"]))
        result = glossary.replace_in_text("达文西是画家")
        assert result == "达芬奇是画家"

    def test_multiple_hotwords(self):
        glossary = HotwordGlossary(lang="zh")
        glossary.add(Hotword(word="达芬奇", aliases=["达文西"]))
        glossary.add(Hotword(word="浩瀚", aliases=["浩瀚"]))
        result = glossary.replace_in_text("达文西和浩瀚")
        assert result == "达芬奇和浩瀚"

    def test_no_match(self):
        glossary = HotwordGlossary(lang="zh")
        glossary.add(Hotword(word="达芬奇", aliases=["达文西"]))
        result = glossary.replace_in_text("苹果公司")
        assert result == "苹果公司"

    def test_empty_glossary(self):
        glossary = HotwordGlossary(lang="zh")
        result = glossary.replace_in_text("达文西是画家")
        assert result == "达文西是画家"


class TestGetAppliedReplacements:
    """Test HotwordGlossary.get_applied_replacements."""

    def test_returns_matching_pairs(self):
        glossary = HotwordGlossary(lang="zh")
        glossary.add(Hotword(word="达芬奇", aliases=["达文西"]))
        result = glossary.get_applied_replacements("达文西是画家")
        assert result == {"达文西": "达芬奇"}

    def test_no_match_returns_empty(self):
        glossary = HotwordGlossary(lang="zh")
        glossary.add(Hotword(word="达芬奇", aliases=["达文西"]))
        result = glossary.get_applied_replacements("苹果公司")
        assert result == {}


class TestHotwordGlossaryFromDisk:
    """Test loading and using glossary from disk."""

    def test_load_and_replace(self, tmp_path):
        glossary_path = tmp_path / "hotwords_zh.txt"
        glossary_path.write_text(
            "达芬奇=达文西,大芬奇\n",
            encoding="utf-8",
        )
        glossary = load_glossary(glossary_path, "zh")
        result = glossary.replace_in_text("达文西是画家")
        assert result == "达芬奇是画家"

    def test_no_glossary_file(self, tmp_path):
        glossary = load_glossary(tmp_path / "nonexistent.txt", "zh")
        result = glossary.replace_in_text("达文西是画家")
        assert result == "达文西是画家"
