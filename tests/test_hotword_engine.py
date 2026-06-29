"""Tests for hotword replacement engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from subtap.glossary.hotword import Hotword, HotwordGlossary
from subtap.glossary.engine import (
    HotwordEngine,
    replace_exact,
    replace_in_text,
)


class TestReplaceExact:
    """Test exact replacement."""

    def test_simple_replace(self):
        result = replace_exact("达文西是画家", "达文西", "达芬奇")
        assert result == "达芬奇是画家"

    def test_multiple_replace(self):
        result = replace_exact("达文西和达文西", "达文西", "达芬奇")
        assert result == "达芬奇和达芬奇"

    def test_no_match(self):
        result = replace_exact("苹果公司", "达文西", "达芬奇")
        assert result == "苹果公司"


class TestReplaceInText:
    """Test text replacement with glossary."""

    def test_single_hotword(self):
        glossary = HotwordGlossary(lang="zh")
        glossary.add(Hotword(word="达芬奇", aliases=["达文西"]))
        result = replace_in_text("达文西是画家", glossary)
        assert result == "达芬奇是画家"

    def test_multiple_hotwords(self):
        glossary = HotwordGlossary(lang="zh")
        glossary.add(Hotword(word="达芬奇", aliases=["达文西"]))
        glossary.add(Hotword(word="浩瀚", aliases=["浩瀚"]))
        result = replace_in_text("达文西和浩瀚", glossary)
        assert result == "达芬奇和浩瀚"

    def test_no_match(self):
        glossary = HotwordGlossary(lang="zh")
        glossary.add(Hotword(word="达芬奇", aliases=["达文西"]))
        result = replace_in_text("苹果公司", glossary)
        assert result == "苹果公司"


class TestHotwordEngine:
    """Test HotwordEngine class."""

    def test_engine_local_mode(self, tmp_path):
        # Create glossary file
        glossary_path = tmp_path / "hotwords_zh.tsv"
        glossary_path.write_text(
            "热词\t错词1\t错词2\t错词3\n达芬奇\t达文西\t大芬奇\t\n",
            encoding="utf-8",
        )

        engine = HotwordEngine(mode="local", glossary_dir=tmp_path)
        result = engine.process("达文西是画家", lang="zh")
        assert result == "达芬奇是画家"

    def test_engine_no_glossary(self, tmp_path):
        engine = HotwordEngine(mode="local", glossary_dir=tmp_path)
        result = engine.process("达文西是画家", lang="zh")
        assert result == "达文西是画家"  # No glossary, no change

    def test_engine_hybrid_mode(self, tmp_path):
        # Create glossary file
        glossary_path = tmp_path / "hotwords_zh.tsv"
        glossary_path.write_text(
            "热词\t错词1\t错词2\t错词3\n达芬奇\t达文西\t大芬奇\t\n",
            encoding="utf-8",
        )

        engine = HotwordEngine(mode="hybrid", glossary_dir=tmp_path)
        result = engine.process("达文西是画家", lang="zh")
        assert result == "达芬奇是画家"
