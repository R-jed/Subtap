"""Tests for hotword learning: LLM discovers → records → writes to local glossary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from subtap.ai.glossary_learner import GlossaryLearner, GlossaryUpdate
from subtap.core.clean import run_clean
from subtap.core.workspace import Workspace
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import ASRSegment


# ── FakeLLM with ops support ─────────────────────────────────


class FakeLLMWithOps:
    """Fake LLM that returns ops from replace_hotwords."""

    def __init__(
        self,
        suspicious: list[int] | None = None,
        repairs: dict[int, str] | None = None,
        hotwords: dict[int, str] | None = None,
        hotword_ops: dict[int, list[dict]] | None = None,
    ):
        self.suspicious = suspicious or []
        self.repairs = repairs or {}
        self.hotwords = hotwords or {}
        self.hotword_ops = hotword_ops or {}
        self.calls: list[str] = []

    def select_suspicious_segments(self, segments: list[dict]) -> list[int]:
        self.calls.append("select")
        return self.suspicious

    def repair_segments(self, segments: list[dict]) -> dict[int, str]:
        self.calls.append("repair")
        return self.repairs

    def replace_hotwords(
        self, segments: list[dict], glossary: dict | None
    ) -> dict[int, dict]:
        """Return {index: {"text": corrected, "ops": [{"from": x, "to": y}]}}."""
        self.calls.append("hotword")
        result = {}
        for idx, text in self.hotwords.items():
            result[idx] = {
                "text": text,
                "ops": self.hotword_ops.get(idx, []),
            }
        return result


# ── Workspace helper ──────────────────────────────────────────


def _workspace(tmp_path: Path, texts: list[str] | None = None) -> Workspace:
    config = SubtapConfig()
    workspace = Workspace(config, base_dir=tmp_path / "work")
    workspace.ensure_dirs()
    rows = [
        ASRSegment(
            chunk_id=0,
            segment_id=index,
            start_sec=float(index),
            end_sec=float(index + 1),
            text=text,
        )
        for index, text in enumerate(texts or ["正常句子", "维图尔XR眼镜"])
    ]
    workspace.asr_jsonl.write_text(
        "".join(row.model_dump_json() + "\n" for row in rows),
        encoding="utf-8",
    )
    return workspace


# ── Test: replace_hotwords returns ops ────────────────────────


class TestReplaceHotwordsReturnsOps:
    """LLM replace_hotwords should return {index: {text, ops}}."""

    def test_returns_text_and_ops(self):
        """replace_hotwords returns dict with text and ops keys."""
        from subtap.backends.llm.openai_compat import OpenAICompatibleLLM

        # This test will fail until we change the return type
        # For now, test via FakeLLMWithOps
        llm = FakeLLMWithOps(
            hotwords={0: "VITURE XR眼镜"},
            hotword_ops={0: [{"from": "维图尔", "to": "VITURE"}]},
        )
        result = llm.replace_hotwords([{"i": 0, "t": "维图尔XR眼镜"}], None)
        assert 0 in result
        assert "text" in result[0]
        assert "ops" in result[0]
        assert result[0]["text"] == "VITURE XR眼镜"
        assert result[0]["ops"] == [{"from": "维图尔", "to": "VITURE"}]


# ── Test: clean.py records ops to workspace ───────────────────


class TestCleanRecordsOps:
    """run_clean should write LLM hotword ops to workspace."""

    def test_records_llm_hotword_ops_to_file(self, tmp_path, monkeypatch):
        """When LLM hotword replaces text, ops are written to llm_hotword_ops.jsonl."""
        workspace = _workspace(tmp_path, ["维图尔XR眼镜"])
        llm = FakeLLMWithOps(
            hotwords={0: "VITURE XR眼镜"},
            hotword_ops={0: [{"from": "维图尔", "to": "VITURE"}]},
        )
        monkeypatch.setattr("subtap.core.clean.get_llm_backend", lambda *_a, **_k: llm)

        config = SubtapConfig()
        config.llm_proofread = False
        config.llm_hotword = True
        run_clean(workspace, config, enhance_mode="api")

        ops_path = workspace.root / "llm_hotword_ops.jsonl"
        assert ops_path.exists(), "llm_hotword_ops.jsonl should be created"
        lines = [json.loads(l) for l in ops_path.read_text().strip().splitlines() if l]
        assert len(lines) == 1
        assert lines[0]["from"] == "维图尔"
        assert lines[0]["to"] == "VITURE"

    def test_no_ops_file_when_no_hotword_replacements(self, tmp_path, monkeypatch):
        """When LLM hotword does nothing, no ops file is created."""
        workspace = _workspace(tmp_path, ["正常句子"])
        llm = FakeLLMWithOps(hotwords={})
        monkeypatch.setattr("subtap.core.clean.get_llm_backend", lambda *_a, **_k: llm)

        config = SubtapConfig()
        config.llm_proofread = False
        config.llm_hotword = True
        run_clean(workspace, config, enhance_mode="api")

        ops_path = workspace.root / "llm_hotword_ops.jsonl"
        assert not ops_path.exists()

    def test_multiple_ops_accumulated(self, tmp_path, monkeypatch):
        """Multiple segments' ops are accumulated in one file."""
        workspace = _workspace(tmp_path, ["维图尔XR眼镜", "理光吉亚四"])
        llm = FakeLLMWithOps(
            hotwords={0: "VITURE XR眼镜", 1: "理光GR IV"},
            hotword_ops={
                0: [{"from": "维图尔", "to": "VITURE"}],
                1: [{"from": "吉亚四", "to": "GR IV"}],
            },
        )
        monkeypatch.setattr("subtap.core.clean.get_llm_backend", lambda *_a, **_k: llm)

        config = SubtapConfig()
        config.llm_proofread = False
        config.llm_hotword = True
        run_clean(workspace, config, enhance_mode="api")

        ops_path = workspace.root / "llm_hotword_ops.jsonl"
        lines = [json.loads(l) for l in ops_path.read_text().strip().splitlines() if l]
        assert len(lines) == 2


# ── Test: GlossaryLearner learns from ops ─────────────────────


class TestGlossaryLearnerFromOps:
    """GlossaryLearner.learn_from_ops() should produce GlossaryUpdate from LLM ops."""

    def test_learn_from_ops_returns_glossary_update(self):
        learner = GlossaryLearner()
        ops = [
            {"from": "维图尔", "to": "VITURE", "segment_id": 0},
            {"from": "吉亚四", "to": "GR IV", "segment_id": 1},
        ]
        result = learner.learn_from_ops(ops)
        assert isinstance(result, GlossaryUpdate)

    def test_learn_from_ops_extracts_new_terms(self):
        learner = GlossaryLearner()
        ops = [
            {"from": "维图尔", "to": "VITURE", "segment_id": 0},
            {"from": "维图尔", "to": "VITURE", "segment_id": 2},
        ]
        result = learner.learn_from_ops(ops)
        assert "VITURE" in result.new_terms
        assert result.new_terms["VITURE"] == "维图尔"

    def test_learn_from_ops_deduplicates(self):
        """Same op appearing multiple times should only appear once."""
        learner = GlossaryLearner()
        ops = [
            {"from": "维图尔", "to": "VITURE", "segment_id": 0},
            {"from": "维图尔", "to": "VITURE", "segment_id": 1},
            {"from": "维图尔", "to": "VITURE", "segment_id": 2},
        ]
        result = learner.learn_from_ops(ops)
        assert len(result.new_terms) == 1

    def test_learn_from_ops_empty(self):
        learner = GlossaryLearner()
        result = learner.learn_from_ops([])
        assert result.new_terms == {}
        assert result.replacement_rules == []


# ── Test: Write learned hotwords to file ──────────────────────


class TestWriteLearnedHotwords:
    """GlossaryUpdate should be writable to hotwords_zh.txt format."""

    def test_writes_hotwords_file(self, tmp_path):
        from subtap.ai.glossary_learner import save_learned_hotwords

        hotwords_path = tmp_path / "hotwords_zh.txt"
        update = GlossaryUpdate(
            new_terms={"VITURE": "维图尔", "GR IV": "吉亚四"},
        )
        save_learned_hotwords(update, hotwords_path)

        content = hotwords_path.read_text(encoding="utf-8")
        assert "VITURE=维图尔" in content
        assert "GR IV=吉亚四" in content

    def test_appends_to_existing_hotwords(self, tmp_path):
        from subtap.ai.glossary_learner import save_learned_hotwords

        hotwords_path = tmp_path / "hotwords_zh.txt"
        hotwords_path.write_text("荣耀=华为荣耀\n", encoding="utf-8")

        update = GlossaryUpdate(new_terms={"VITURE": "维图尔"})
        save_learned_hotwords(update, hotwords_path)

        content = hotwords_path.read_text(encoding="utf-8")
        assert "荣耀=华为荣耀" in content
        assert "VITURE=维图尔" in content

    def test_deduplicates_existing_hotwords(self, tmp_path):
        from subtap.ai.glossary_learner import save_learned_hotwords

        hotwords_path = tmp_path / "hotwords_zh.txt"
        hotwords_path.write_text("VITURE=维图尔\n", encoding="utf-8")

        update = GlossaryUpdate(new_terms={"VITURE": "维图尔"})
        save_learned_hotwords(update, hotwords_path)

        content = hotwords_path.read_text(encoding="utf-8")
        assert content.count("VITURE=维图尔") == 1
