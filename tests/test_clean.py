"""Tests for clean pipeline stage: glossary + replacement + LLM."""

from __future__ import annotations

from pathlib import Path

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
    clean_module.get_llm_backend = lambda cfg: None  # type: ignore
    try:
        result = run_clean(ws, test_config, glossary_path=str(glossary_yaml))
    finally:
        clean_module.get_llm_backend = original_get

    assert result["segment_count"] == 2
    assert ws.cleaned_jsonl.exists()

    lines = ws.cleaned_jsonl.read_text().strip().split("\n")
    segs = [CleanSegment.model_validate_json(line) for line in lines]
    assert segs[0].cleaned_text == "machine learning is great"
    assert segs[1].cleaned_text == "New York city"
    assert "maching learning→machine learning" in segs[0].glossary_applied


def test_clean_jsonl_valid_schema(test_config: SubtapConfig, tmp_path: Path):
    """cleaned.jsonl contains valid CleanSegment JSONL."""
    ws = Workspace(test_config, base_dir=tmp_path / "work")
    ws.ensure_dirs()
    _make_asr_jsonl(ws, ["test text one", "test text two"])

    import subtap.core.clean as clean_module

    original_get = clean_module.get_llm_backend
    clean_module.get_llm_backend = lambda cfg: None  # type: ignore
    try:
        run_clean(ws, test_config)
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
    clean_module.get_llm_backend = lambda cfg: None  # type: ignore
    try:
        pipeline = Pipeline(test_config, work_dir=tmp_path / "work")
        result = pipeline.run_stage("clean")
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

    monkeypatch.setattr(clean_module, "get_llm_backend", lambda cfg: None)
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
            "mock:dummy",
        ],
    )
    assert result.exit_code == 0
    assert "完成" in result.output
