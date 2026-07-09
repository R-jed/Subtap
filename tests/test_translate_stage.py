from __future__ import annotations

from pathlib import Path

import pytest

from subtap.core.translate import (
    _blocks_to_srt,
    _build_chunk_prompt,
    _chunk_and_translate,
    parse_srt,
    render_srt_from_aligned,
    run_translate,
    validate_translated_srt,
)
from subtap.core.workspace import Workspace
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import AlignedSegment


class FakeTranslator:
    def __init__(self, translated_srt: str | None = None):
        self.translated_srt = translated_srt
        self.input_srt = ""
        self.target_language = ""
        self.custom_prompt = ""
        self.call_count = 0
        self.calls: list[tuple[str, str, str | None]] = []

    def translate_srt(
        self,
        srt_text: str,
        target_language: str,
        custom_prompt: str | None = None,
    ) -> str:
        self.input_srt = srt_text
        self.target_language = target_language
        self.custom_prompt = custom_prompt or ""
        self.call_count += 1
        self.calls.append((srt_text, target_language, custom_prompt))
        if self.translated_srt:
            return self.translated_srt
        # Default: return input as-is (identity translation)
        return srt_text


def _workspace(tmp_path: Path) -> Workspace:
    config = SubtapConfig()
    workspace = Workspace(config, base_dir=tmp_path / "work")
    workspace.ensure_dirs()
    rows = [
        AlignedSegment(
            sentence_id=0,
            start_sec=1.0,
            end_sec=2.0,
            text="理光 GR4 发布了",
            words=[],
        ),
        AlignedSegment(
            sentence_id=1,
            start_sec=2.0,
            end_sec=3.5,
            text="这是一台相机",
            words=[],
        ),
    ]
    workspace.aligned_jsonl.write_text(
        "".join(row.model_dump_json() + "\n" for row in rows),
        encoding="utf-8",
    )
    return workspace


def test_render_srt_from_aligned_uses_enhanced_aligned_text(tmp_path):
    workspace = _workspace(tmp_path)
    srt_text = render_srt_from_aligned(workspace.aligned_jsonl)

    assert "理光 GR4 发布了" in srt_text
    assert "00:00:01,000 --> 00:00:02,000" in srt_text


def test_parse_srt_reads_index_time_and_text():
    blocks = parse_srt("1\n00:00:01,000 --> 00:00:02,000\nHello\n")

    assert blocks == [
        {
            "index": 1,
            "start": "00:00:01,000",
            "end": "00:00:02,000",
            "text": "Hello",
        }
    ]


def test_validate_translated_srt_rejects_time_changes():
    source = parse_srt("1\n00:00:01,000 --> 00:00:02,000\n源文\n")
    translated = parse_srt("1\n00:00:01,100 --> 00:00:02,000\nHello\n")

    with pytest.raises(ValueError, match="时间轴不一致"):
        validate_translated_srt(source, translated)


def test_run_translate_writes_translated_text(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    translated = (
        "1\n00:00:01,000 --> 00:00:02,000\nRicoh GR4 was released\n\n"
        "2\n00:00:02,000 --> 00:00:03,500\nThis is a camera\n"
    )
    llm = FakeTranslator(translated)
    monkeypatch.setattr("subtap.core.translate.get_translator", lambda *_a, **_k: llm)

    result = run_translate(workspace, SubtapConfig(), target_language="en")

    assert result["translated_count"] == 2
    assert llm.target_language == "en"
    assert "理光 GR4 发布了" in llm.input_srt
    payload = workspace.aligned_jsonl.read_text(encoding="utf-8")
    assert "Ricoh GR4 was released" in payload
    assert "This is a camera" in payload


def test_run_translate_rejects_non_openai_backend(tmp_path):
    workspace = _workspace(tmp_path)

    with pytest.raises(ValueError, match="翻译只支持 OpenAI-compatible"):
        run_translate(
            workspace,
            SubtapConfig(),
            target_language="en",
            llm_backend_name="invalid-backend",
        )


def _make_blocks(n: int) -> list[dict]:
    """Generate n SRT blocks for testing."""
    blocks = []
    for i in range(1, n + 1):
        blocks.append({
            "index": i,
            "start": f"00:00:{i:02d},000",
            "end": f"00:00:{i + 1:02d},000",
            "text": f"原文第{i}句",
        })
    return blocks


def test_blocks_to_srt_roundtrip():
    blocks = _make_blocks(3)
    srt = _blocks_to_srt(blocks)
    parsed = parse_srt(srt)
    assert parsed == blocks


def test_build_chunk_prompt_has_markers():
    ctx_before = _blocks_to_srt(_make_blocks(1))
    to_translate = _blocks_to_srt(_make_blocks(2))
    ctx_after = _blocks_to_srt(_make_blocks(1))

    prompt = _build_chunk_prompt(ctx_before, to_translate, ctx_after, "en")

    assert "【上文参考】" in prompt
    assert "【待翻译】" in prompt
    assert "【下文参考】" in prompt
    assert "翻译为en" in prompt


def test_build_chunk_prompt_no_context():
    to_translate = _blocks_to_srt(_make_blocks(2))
    prompt = _build_chunk_prompt("", to_translate, "", "en")

    assert "【上文参考】" not in prompt
    assert "【待翻译】" in prompt
    assert "【下文参考】" not in prompt


def test_chunk_and_translate_small_input():
    """输入少于 CHUNK_SIZE 时，应该一次性翻译。"""
    source_blocks = _make_blocks(5)
    llm = FakeTranslator()

    translated = _chunk_and_translate(llm, source_blocks, "en")

    assert llm.call_count == 1
    assert len(translated) == 5


def test_chunk_and_translate_exact_chunk_size():
    """输入恰好等于 CHUNK_SIZE 时，应该一次性翻译。"""
    source_blocks = _make_blocks(30)
    llm = FakeTranslator()

    translated = _chunk_and_translate(llm, source_blocks, "en")

    assert llm.call_count == 1
    assert len(translated) == 30


def test_chunk_and_translate_multiple_chunks():
    """输入超过 CHUNK_SIZE 时，应该分块翻译。"""
    source_blocks = _make_blocks(65)
    llm = FakeTranslator()

    translated = _chunk_and_translate(llm, source_blocks, "en")

    # 65 / 30 = 3 chunks (30, 30, 5)
    assert llm.call_count == 3
    assert len(translated) == 65


def test_chunk_and_translate_preserves_order():
    """分块翻译后，结果顺序应该与输入一致。"""
    source_blocks = _make_blocks(65)
    llm = FakeTranslator()

    translated = _chunk_and_translate(llm, source_blocks, "en")

    for i, block in enumerate(translated):
        assert block["index"] == i + 1


def test_chunk_and_translate_uses_custom_prompt():
    """分块翻译应该使用自定义 prompt。"""
    source_blocks = _make_blocks(5)
    llm = FakeTranslator()

    _chunk_and_translate(llm, source_blocks, "en")

    assert "【待翻译】" in llm.custom_prompt
    assert "翻译为en" in llm.custom_prompt


def test_chunk_and_translate_with_context():
    """多块时，中间块应该包含上下文。"""
    source_blocks = _make_blocks(65)
    llm = FakeTranslator()

    _chunk_and_translate(llm, source_blocks, "en")

    # 第一块：无上文，有下文（3句）
    first_prompt = llm.calls[0][2]
    assert "【上文参考】" not in first_prompt
    assert "【下文参考】" in first_prompt

    # 第二块：有上文（3句），有下文（3句）
    second_prompt = llm.calls[1][2]
    assert "【上文参考】" in second_prompt
    assert "【下文参考】" in second_prompt

    # 第三块：有上文（3句），无下文
    third_prompt = llm.calls[2][2]
    assert "【上文参考】" in third_prompt
    assert "【下文参考】" not in third_prompt


def test_run_translate_uses_chunked_translation(tmp_path, monkeypatch):
    """run_translate 应该使用分块翻译。"""
    workspace = _workspace(tmp_path)
    llm = FakeTranslator()
    monkeypatch.setattr("subtap.core.translate.get_translator", lambda *_a, **_k: llm)

    result = run_translate(workspace, SubtapConfig(), target_language="en")

    assert result["translated_count"] == 2
    assert llm.call_count == 1  # 只有2句，不需要分块
