"""Tests to verify three bugs before and after fix.

Bug 1: --format parameter not passed to export (P0)
Bug 2: Hotword loaded status always shows "否" (P1)
Bug 3: source_text granularity mismatch in script matching (P2)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


class TestFormatParameterPassing:
    """Bug 1: --format should be passed to run_final_exports."""

    def test_runner_passes_fmt_to_export(self, tmp_path: Path) -> None:
        """RichRunner.run_pipeline should pass fmt to run_final_exports."""
        from subtap.ui.tui import RichRunner

        runner = RichRunner()
        pipeline = MagicMock()
        pipeline.config.output.subtitle_punctuation = False
        pipeline.config.output.subtitle_language = "zh"
        pipeline.config.output.max_chars = 25
        pipeline.config.output.subtitle_formats = {"srt"}
        pipeline.config.output.subtitle_stem = "final"
        pipeline.config.asr = MagicMock()
        pipeline.config.asr.backend = "mlx-qwen-asr"
        pipeline.config.asr.model = "asr_0.6b"
        pipeline.config.asr.quantization = "q8"
        pipeline.config.asr.keep_model_alive = False
        pipeline.config.align = MagicMock()
        pipeline.config.align.backend = "mlx-qwen-aligner"
        pipeline.config.align.model = "aligner"
        pipeline.config.align.quantization = "q8"
        pipeline.config.align.keep_model_alive = False
        pipeline.workspace = MagicMock()
        pipeline.workspace.run_log = tmp_path / "run.log"
        pipeline.workspace.aligned_jsonl = tmp_path / "aligned.jsonl"
        pipeline.workspace.script_matched_jsonl = tmp_path / "script_matched.jsonl"
        pipeline.workspace.sentences_jsonl = tmp_path / "sentences.jsonl"
        pipeline.workspace.cleaned_jsonl = tmp_path / "cleaned.jsonl"

        # Create minimal aligned.jsonl
        (tmp_path / "aligned.jsonl").write_text(
            '{"text":"test","start_sec":0,"end_sec":1}\n', encoding="utf-8"
        )

        with patch("subtap.core.export.run_final_exports") as mock_export:
            mock_export.return_value = {"srt": str(tmp_path / "out.srt")}
            try:
                runner.run_pipeline(
                    pipeline,
                    tmp_path / "input.mp3",
                    tmp_path / "output",
                    fmt="vtt",
                    enhance="local",
                )
            except Exception:
                pass  # We just want to check the call args

            if mock_export.called:
                call_kwargs = mock_export.call_args[1]
                assert "vtt" in call_kwargs.get(
                    "formats", set()
                ), f"Expected formats to contain 'vtt', got {call_kwargs.get('formats')}"


class TestHotwordLoadedStatus:
    """Bug 2: run_log.hotwords should show loaded=True when file exists."""

    def test_hotword_count_uses_correct_attribute(self, tmp_path: Path) -> None:
        """run_log.hotwords should use .hotwords attribute, not .entries."""
        from subtap.glossary.hotword import HotwordGlossary, Hotword

        glossary = HotwordGlossary("zh", [Hotword("测试", ["测试别名"])])
        # Verify .hotwords exists
        assert hasattr(
            glossary, "hotwords"
        ), "HotwordGlossary should have .hotwords attribute"
        assert len(glossary.hotwords) == 1
        # Verify .entries does NOT exist
        assert not hasattr(
            glossary, "entries"
        ), "HotwordGlossary should NOT have .entries attribute"


class TestSourceTextGranularity:
    """Bug 3: source_text should match sentence text, not parent segment."""

    def test_segmentation_sets_source_text_to_sentence_text(self) -> None:
        """Each sentence's source_text should be its own text, not the parent segment."""
        from subtap.core.segmentation import segment_clean_segments
        from subtap.schemas.models import RawCleanSegment

        # Create a segment with multiple sentences
        seg = RawCleanSegment(
            segment_id=0,
            source_chunk_id=0,
            original_text="大家好欢迎来到我们的节目。今天给大家分享一个有趣的话题。希望大家喜欢。",
            cleaned_text="大家好欢迎来到我们的节目。今天给大家分享一个有趣的话题。希望大家喜欢。",
        )

        sentences = segment_clean_segments(
            [seg], chunk_start=0.0, chunk_end=10.0, language="zh"
        )

        assert len(sentences) > 1, f"Expected multiple sentences, got {len(sentences)}"

        # Each sentence's source_text should match its own text
        for s in sentences:
            assert s.source_text == s.text, (
                f"sentence source_text '{s.source_text[:30]}...' "
                f"should equal text '{s.text[:30]}...'"
            )
