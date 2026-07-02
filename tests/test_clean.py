"""Tests for clean pipeline stage: glossary + replacement + LLM."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from helpers import MockLLMBackend

from subtap.core.clean import run_clean
from subtap.core.replacement import apply_replacements
from subtap.core.workspace import Workspace
from subtap.schemas.config import SubtapConfig
from subtap.schemas.glossary import (
    Glossary,
    GlossaryTerm,
    GlossaryReplacement,
    load_glossary,
)
from subtap.schemas.models import ASRSegment, CleanSegment

# ── Glossary tests ──


def test_load_glossary_from_yaml(tmp_path: Path):
    """Glossary loaded from YAML with terms, replacements, style."""
    yaml_content = """
terms:
  - canonical: Python
    aliases: [python, PYTHON, py]
  - canonical: JavaScript
    aliases: [javascript, JS]
replacements:
  - find: maching learning
    replace: machine learning
  - find: NEW YORK
    replace: New York
style:
  - Use formal register
  - No contractions
"""
    gpath = tmp_path / "glossary.yaml"
    gpath.write_text(yaml_content)

    glossary = load_glossary(gpath)
    assert len(glossary.terms) == 2
    assert len(glossary.replacements) == 2
    assert len(glossary.style) == 2
    assert glossary.style[0] == "Use formal register"


def test_glossary_alias_resolution():
    """Alias → canonical mapping (case-insensitive)."""
    glossary = Glossary(
        terms=[
            GlossaryTerm(canonical="Python", aliases=["python", "PYTHON", "py"]),
        ],
    )
    assert glossary.resolve_alias("python") == "Python"
    assert glossary.resolve_alias("PYTHON") == "Python"
    assert glossary.resolve_alias("Py") == "Python"
    assert glossary.resolve_alias("Java") == "Java"  # unknown → return as-is


def test_load_glossary_none():
    """Loading with None path returns empty glossary."""
    g = load_glossary(None)
    assert len(g.terms) == 0
    assert len(g.replacements) == 0


def test_load_glossary_missing_file():
    """Loading with non-existent file returns empty glossary."""
    g = load_glossary(Path("/nonexistent.yaml"))
    assert len(g.terms) == 0


# ── Deterministic replacement tests ──


def test_apply_replacements_basic():
    """Replacements modify text and track applied rules."""
    glossary = Glossary(
        replacements=[
            GlossaryReplacement(find="maching learning", replace="machine learning"),
            GlossaryReplacement(find="NEW YORK", replace="New York"),
        ],
    )
    segments = [
        ASRSegment(
            chunk_id=0,
            segment_id=0,
            start_sec=0.0,
            end_sec=2.0,
            text="We use maching learning in NEW YORK",
        ),
    ]
    result = apply_replacements(segments, glossary)

    assert len(result) == 1
    assert result[0].cleaned_text == "We use machine learning in New York"
    assert result[0].original_text == "We use maching learning in NEW YORK"
    assert len(result[0].glossary_applied) == 2


def test_apply_replacements_case_insensitive():
    """Case-insensitive matching."""
    glossary = Glossary(
        replacements=[GlossaryReplacement(find="hello", replace="Hello")],
    )
    segments = [
        ASRSegment(
            chunk_id=0,
            segment_id=0,
            start_sec=0.0,
            end_sec=1.0,
            text="HELLO world hello",
        ),
    ]
    result = apply_replacements(segments, glossary)
    assert result[0].cleaned_text == "Hello world Hello"


def test_apply_replacements_no_match():
    """When no replacements match, text is unchanged."""
    glossary = Glossary(
        replacements=[GlossaryReplacement(find="xyz", replace="abc")],
    )
    segments = [
        ASRSegment(
            chunk_id=0, segment_id=0, start_sec=0.0, end_sec=1.0, text="no match here"
        ),
    ]
    result = apply_replacements(segments, glossary)
    assert result[0].cleaned_text == "no match here"
    assert result[0].glossary_applied == []


def test_apply_replacements_empty_glossary():
    """Empty glossary passes through unchanged."""
    segments = [
        ASRSegment(
            chunk_id=0, segment_id=0, start_sec=0.0, end_sec=1.0, text="unchanged"
        ),
    ]
    result = apply_replacements(segments, None)
    assert result[0].cleaned_text == "unchanged"


# ── Clean pipeline tests ──


def _make_asr_jsonl(ws: Workspace, texts: list[str]) -> None:
    """Write mock ASR segments to asr.jsonl."""
    ws.asr_dir.mkdir(parents=True, exist_ok=True)
    with open(ws.asr_jsonl, "w") as f:
        for i, text in enumerate(texts):
            seg = ASRSegment(
                chunk_id=i,
                segment_id=i,
                start_sec=float(i),
                end_sec=float(i + 1),
                text=text,
            )
            f.write(seg.model_dump_json() + "\n")


def test_clean_pipeline_replacement_only(test_config: SubtapConfig, tmp_path: Path):
    """Clean stage with replacement-only (no LLM)."""
    ws = Workspace(test_config, base_dir=tmp_path / "work")
    ws.ensure_dirs()
    _make_asr_jsonl(ws, ["maching learning is great", "NEW YORK city"])

    # Create glossary
    glossary_yaml = tmp_path / "glossary.yaml"
    glossary_yaml.write_text("""
replacements:
  - find: maching learning
    replace: machine learning
  - find: NEW YORK
    replace: New York
""")

    # Patch get_llm_backend to return a no-op
    import subtap.core.clean as clean_module

    original_get = clean_module.get_llm_backend
    clean_module.get_llm_backend = lambda cfg, remote_api=None: None  # type: ignore
    try:
        result = run_clean(ws, test_config, glossary_path=str(glossary_yaml), enhance_mode="local")
    finally:
        clean_module.get_llm_backend = original_get

    assert result["segment_count"] == 2
    assert ws.cleaned_jsonl.exists()

    lines = ws.cleaned_jsonl.read_text().strip().split("\n")
    segs = [CleanSegment.model_validate_json(line) for line in lines]
    assert segs[0].cleaned_text == "machine learning is great"
    assert segs[1].cleaned_text == "New York city"
    assert "maching learning→machine learning" in segs[0].glossary_applied


def test_clean_local_mode_does_not_call_llm(
    test_config: SubtapConfig, tmp_path: Path, monkeypatch
):
    """local 模式下，clean 阶段只做本地清洗，不触发 LLM 后端。"""
    ws = Workspace(test_config, base_dir=tmp_path / "work")
    ws.ensure_dirs()
    _make_asr_jsonl(ws, ["hello  world"])
    called = {"count": 0}

    def fail_if_called(*_args, **_kwargs):
        called["count"] += 1
        raise AssertionError("LLM backend must not be called in local mode")

    monkeypatch.setattr("subtap.core.clean.get_llm_backend", fail_if_called)

    result = run_clean(ws, test_config, enhance_mode="local")

    assert result["segment_count"] == 1
    assert called["count"] == 0
    seg = CleanSegment.model_validate_json(ws.cleaned_jsonl.read_text().strip())
    assert seg.cleaned_text == "hello world"


def test_segments_for_llm_uses_global_index(test_config: SubtapConfig, tmp_path: Path):
    """_segments_for_llm 应该使用全局索引而不是 segment_id。"""
    from subtap.core.clean import _segments_for_llm

    # 模拟多个 chunk 的情况，每个 chunk 的 segment_id 都从 0 开始
    segments = [
        CleanSegment(
            chunk_id=0,
            segment_id=0,
            start_sec=0.0,
            end_sec=1.0,
            original_text="text0",
            cleaned_text="clean0",
        ),
        CleanSegment(
            chunk_id=1,
            segment_id=0,  # 同样的 segment_id
            start_sec=1.0,
            end_sec=2.0,
            original_text="text1",
            cleaned_text="clean1",
        ),
        CleanSegment(
            chunk_id=2,
            segment_id=0,  # 同样的 segment_id
            start_sec=2.0,
            end_sec=3.0,
            original_text="text2",
            cleaned_text="clean2",
        ),
    ]

    result = _segments_for_llm(segments)

    # 应该使用全局索引 0, 1, 2，而不是 segment_id 0, 0, 0
    assert len(result) == 3
    assert result[0]["i"] == 0
    assert result[1]["i"] == 1
    assert result[2]["i"] == 2
    assert result[0]["t"] == "clean0"
    assert result[1]["t"] == "clean1"
    assert result[2]["t"] == "clean2"


def test_apply_text_updates_uses_global_index(test_config: SubtapConfig, tmp_path: Path):
    """_apply_text_updates 应该使用全局索引来更新 segment。"""
    from subtap.core.clean import _apply_text_updates

    # 模拟多个 chunk 的情况，每个 chunk 的 segment_id 都从 0 开始
    segments = [
        CleanSegment(
            chunk_id=0,
            segment_id=0,
            start_sec=0.0,
            end_sec=1.0,
            original_text="text0",
            cleaned_text="clean0",
        ),
        CleanSegment(
            chunk_id=1,
            segment_id=0,  # 同样的 segment_id
            start_sec=1.0,
            end_sec=2.0,
            original_text="text1",
            cleaned_text="clean1",
        ),
        CleanSegment(
            chunk_id=2,
            segment_id=0,  # 同样的 segment_id
            start_sec=2.0,
            end_sec=3.0,
            original_text="text2",
            cleaned_text="clean2",
        ),
    ]

    # 模拟 LLM 返回的更新，使用全局索引
    updates = {0: "updated0", 1: "updated1", 2: "updated2"}

    _apply_text_updates(segments, updates)

    # 验证每个 segment 都被正确更新
    assert segments[0].cleaned_text == "updated0"
    assert segments[1].cleaned_text == "updated1"
    assert segments[2].cleaned_text == "updated2"


def test_clean_jsonl_valid_schema(test_config: SubtapConfig, tmp_path: Path):
    """cleaned.jsonl contains valid CleanSegment JSONL."""
    ws = Workspace(test_config, base_dir=tmp_path / "work")
    ws.ensure_dirs()
    _make_asr_jsonl(ws, ["test text one", "test text two"])

    import subtap.core.clean as clean_module

    original_get = clean_module.get_llm_backend
    clean_module.get_llm_backend = lambda cfg, remote_api=None: None  # type: ignore
    try:
        run_clean(ws, test_config, enhance_mode="local")
    finally:
        clean_module.get_llm_backend = original_get

    with open(ws.cleaned_jsonl) as f:
        for line in f:
            seg = CleanSegment.model_validate_json(line.strip())
            assert seg.segment_id >= 0
            assert seg.original_text
            assert seg.cleaned_text


def test_clean_stage_in_pipeline(test_config: SubtapConfig, tmp_path: Path):
    """Pipeline.run_stage('clean') works end-to-end."""
    from subtap.core.pipeline import Pipeline

    ws = Workspace(test_config, base_dir=tmp_path / "work")
    ws.ensure_dirs()
    _make_asr_jsonl(ws, ["hello world"])

    import subtap.core.clean as clean_module

    original_get = clean_module.get_llm_backend
    clean_module.get_llm_backend = lambda cfg, remote_api=None: None  # type: ignore
    try:
        pipeline = Pipeline(test_config, work_dir=tmp_path / "work")
        result = pipeline.run_stage("clean", enhance_mode="local")
    finally:
        clean_module.get_llm_backend = original_get

    assert result["segment_count"] == 1
    assert Path(result["cleaned_jsonl"]).exists()


# ── Local text cleaning tests ──


def test_local_clean_normalizes_unicode():
    """Local clean should normalize unicode."""
    from subtap.core.clean import local_clean_text

    result = local_clean_text("你好世界")
    assert result == "你好世界"


def test_local_clean_normalizes_fullwidth_digits():
    """Local clean should normalize full-width digits."""
    from subtap.core.clean import local_clean_text

    result = local_clean_text("第１２３章")
    assert result == "第123章"


def test_local_clean_removes_extra_spaces():
    """Local clean should remove extra spaces."""
    from subtap.core.clean import local_clean_text

    result = local_clean_text("你好  世界")
    assert result == "你好 世界"


def test_local_clean_applies_glossary():
    """Local clean should apply glossary replacements."""
    from subtap.core.clean import local_clean_text

    result = local_clean_text("测试", glossary={"测试": "测试"})
    assert result == "测试"


def test_local_clean_empty_text():
    """Local clean should handle empty text."""
    from subtap.core.clean import local_clean_text

    result = local_clean_text("")
    assert result == ""


def test_local_clean_no_glossary():
    """Local clean should work without glossary."""
    from subtap.core.clean import local_clean_text

    result = local_clean_text("正常文本")
    assert result == "正常文本"


def test_cli_clean_runnable(test_config: SubtapConfig, tmp_path: Path, monkeypatch):
    """CLI clean command runs without crash."""
    from typer.testing import CliRunner
    from subtap.cli import app

    ws = Workspace(test_config, base_dir=tmp_path / "work")
    ws.ensure_dirs()
    _make_asr_jsonl(ws, ["cli test segment"])

    # Patch
    import subtap.core.clean as clean_module

    monkeypatch.setattr(clean_module, "get_llm_backend", lambda cfg, remote_api=None: None)
    import subtap.schemas.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "load_config", lambda p: test_config)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "clean",
            str(ws.asr_jsonl),
            "-w",
            str(ws.root),
            "--llm",
            "off",
        ],
    )
    assert result.exit_code == 0
    assert "完成" in result.output


# ── Independent LLM config tests ──


@pytest.fixture
def workspace(tmp_path):
    """Create a test workspace with mock ASR data."""
    config = SubtapConfig()
    ws = Workspace(config, base_dir=tmp_path / "work")
    ws.ensure_dirs()
    _make_asr_jsonl(ws, ["hello world", "test segment"])
    return ws


def test_run_clean_uses_llm_proofread_config(workspace):
    """run_clean 应使用 llm_proofread 配置项"""
    config = SubtapConfig()
    config.llm_proofread = True
    config.llm_hotword = False

    mock_llm = MockLLMBackend()

    with patch("subtap.core.clean.get_llm_backend", return_value=mock_llm):
        result = run_clean(workspace, config)

    # 验证 LLM 校对被调用
    assert mock_llm.select_suspicious_segments_called is True
    assert mock_llm.repair_segments_called is True
    # 验证热词替换未被调用（因为 llm_hotword=False）
    assert mock_llm.replace_hotwords_called is False


def test_run_clean_uses_llm_hotword_config(workspace):
    """run_clean 应使用 llm_hotword 配置项"""
    config = SubtapConfig()
    config.llm_proofread = False
    config.llm_hotword = True

    mock_llm = MockLLMBackend()

    # 创建 glossary 以提供 hotword_payload
    mock_glossary = Glossary(
        terms=[GlossaryTerm(canonical="test", aliases=["Test"])]
    )

    with patch("subtap.core.clean.get_llm_backend", return_value=mock_llm), \
         patch("subtap.core.clean.load_glossary", return_value=mock_glossary):
        result = run_clean(workspace, config)

    # 验证 LLM 校对未被调用（因为 llm_proofread=False）
    assert mock_llm.select_suspicious_segments_called is False
    assert mock_llm.repair_segments_called is False
    # 验证热词替换被调用
    assert mock_llm.replace_hotwords_called is True


def test_run_clean_skips_llm_when_both_disabled(workspace):
    """run_clean 应在两个开关都关闭时跳过 LLM"""
    config = SubtapConfig()
    config.llm_proofread = False
    config.llm_hotword = False

    mock_llm = MockLLMBackend()

    with patch("subtap.core.clean.get_llm_backend", return_value=mock_llm):
        result = run_clean(workspace, config)

    # 验证 LLM 未被调用
    assert mock_llm.select_suspicious_segments_called is False
    assert mock_llm.repair_segments_called is False
    assert mock_llm.replace_hotwords_called is False


def test_run_clean_both_enabled(workspace):
    """run_clean 应在两个开关都开启时同时调用校对和热词"""
    config = SubtapConfig()
    config.llm_proofread = True
    config.llm_hotword = True

    mock_llm = MockLLMBackend()

    # 创建 glossary 以提供 hotword_payload
    mock_glossary = Glossary(
        terms=[GlossaryTerm(canonical="test", aliases=["Test"])]
    )

    with patch("subtap.core.clean.get_llm_backend", return_value=mock_llm), \
         patch("subtap.core.clean.load_glossary", return_value=mock_glossary):
        result = run_clean(workspace, config)

    # 验证两个功能都被调用
    assert mock_llm.select_suspicious_segments_called is True
    assert mock_llm.repair_segments_called is True
    assert mock_llm.replace_hotwords_called is True


def test_run_clean_enhance_mode_local_overrides_config(workspace):
    """enhance_mode='local' 应覆盖独立配置项，禁用所有 LLM 功能"""
    config = SubtapConfig()
    config.llm_proofread = True
    config.llm_hotword = True

    mock_llm = MockLLMBackend()

    with patch("subtap.core.clean.get_llm_backend", return_value=mock_llm):
        result = run_clean(workspace, config, enhance_mode="local")

    # enhance_mode="local" 应该禁用所有 LLM 功能
    assert mock_llm.select_suspicious_segments_called is False
    assert mock_llm.repair_segments_called is False
    assert mock_llm.replace_hotwords_called is False


def test_run_clean_llm_backend_name_local_overrides_config(workspace):
    """llm_backend_name='local' 应覆盖独立配置项，禁用所有 LLM 功能"""
    config = SubtapConfig()
    config.llm_proofread = True
    config.llm_hotword = True

    mock_llm = MockLLMBackend()

    with patch("subtap.core.clean.get_llm_backend", return_value=mock_llm):
        result = run_clean(workspace, config, enhance_mode="local")

    # enhance_mode="local" 应该禁用所有 LLM 功能
    assert mock_llm.select_suspicious_segments_called is False
    assert mock_llm.repair_segments_called is False
    assert mock_llm.replace_hotwords_called is False
