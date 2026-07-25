"""Helper script for C3 subprocess tests.

Invoked by test subprocesses to exercise the real production pipeline path
with mocked underlying functions.  Never called directly from pytest.

Environment variables:
    C3_TEST_MODE: "normal" | "crash_at_asr" | "crash_at_script_match" |
                  "crash_at_translate"
    C3_INPUT_PATH, C3_WORK_DIR, C3_OUTPUT_DIR: required paths
    C3_SCRIPT_PATH: optional, enables script_match stage
    C3_TRANSLATE_TO: optional, enables translate stage
    C3_GLOSSARY_PATH: optional, passed to hotword/learn stages
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Pre-mock heavy native modules that may not be installed
for mod_name in ["sherpa_onnx", "mlx", "mlx.core", "mlx.audio"]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()


def _mock_all_stages():
    """Replace all heavy stage handlers' inner functions with fakes."""
    import subtap.core.media as media_mod
    import subtap.core.vad as vad_mod
    import subtap.core.asr as asr_mod
    import subtap.core.clean as clean_mod
    import subtap.core.segment as segment_mod
    import subtap.core.align as align_mod
    import subtap.core.export as export_mod
    import subtap.core.hotword as hotword_mod

    media_mod.prepare_media = MagicMock(
        return_value=MagicMock(
            model_dump=lambda: {"duration": 10.0, "sample_rate": 16000}
        )
    )
    vad_mod.split_chunks = MagicMock(return_value=[])
    asr_mod.run_asr = MagicMock(return_value={"segment_count": 1})
    clean_mod.run_clean = MagicMock(return_value={"segment_count": 1})
    segment_mod.run_segment = MagicMock(return_value={"sentence_count": 1})
    align_mod.run_align = MagicMock(return_value={"aligned_count": 1})
    export_mod.run_final_exports = MagicMock(
        return_value={"output_path": "x.srt", "segment_count": 1}
    )
    hotword_mod.run_hotword = MagicMock(return_value={"replaced": 0, "total": 0})


def main():
    mode = os.environ.get("C3_TEST_MODE", "normal")

    _mock_all_stages()

    if mode == "crash_at_asr":
        import subtap.core.asr as asr_mod

        asr_mod.run_asr = MagicMock(side_effect=lambda *a, **kw: os._exit(99))

    if mode == "crash_at_script_match":
        from subtap.script import match as match_mod

        def _crash_script_match(*a, **kw):
            os._exit(97)

        match_mod.match_from_file = _crash_script_match

    if mode == "crash_at_translate":
        from subtap.core import translate as translate_mod

        def _crash_translate(*a, **kw):
            os._exit(96)

        translate_mod.run_translate = _crash_translate

    input_path = Path(os.environ["C3_INPUT_PATH"])
    work_dir = Path(os.environ["C3_WORK_DIR"])
    output_dir = Path(os.environ["C3_OUTPUT_DIR"])

    script_path = os.environ.get("C3_SCRIPT_PATH", "")
    translate_to = os.environ.get("C3_TRANSLATE_TO", "")
    glossary_path = os.environ.get("C3_GLOSSARY_PATH", "")

    from subtap.schemas.config import SubtapConfig
    from subtap.core.tracked_pipeline import TrackedPipeline
    from subtap.ui.tui import RichRunner

    config = SubtapConfig()
    if script_path:
        config.output.script_path = script_path
    if glossary_path:
        config.clean.glossary_path = glossary_path

    pipeline = TrackedPipeline(config, work_dir=work_dir)
    pipeline.workspace.ensure_dirs()

    # Create minimal sentences.jsonl for script_match to read
    if script_path:
        pipeline.workspace.sentences_jsonl.write_text(
            '{"sentence_id":0,"text":"test","start_sec":0,"end_sec":1}\n',
            encoding="utf-8",
        )

    runner = RichRunner()
    runner.run_pipeline(
        pipeline,
        input_path,
        output_dir,
        fmt="srt",
        enhance="local",
        translate_to=translate_to or None,
    )


if __name__ == "__main__":
    main()
