"""Helper script for C3 subprocess tests.

Invoked by test subprocesses to exercise the real production pipeline path
with mocked underlying functions.  Never called directly from pytest.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock


def _mock_all_stages():
    """Replace all heavy stage handlers' inner functions with fakes."""
    import subtap.core.media as media_mod
    import subtap.core.vad as vad_mod
    import subtap.core.asr as asr_mod
    import subtap.core.clean as clean_mod
    import subtap.core.segment as segment_mod
    import subtap.core.align as align_mod
    import subtap.core.export as export_mod

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


def main():
    mode = os.environ.get("C3_TEST_MODE", "normal")

    _mock_all_stages()

    if mode == "crash_at_asr":
        import subtap.core.asr as asr_mod

        asr_mod.run_asr = MagicMock(side_effect=lambda *a, **kw: os._exit(99))

    input_path = Path(os.environ["C3_INPUT_PATH"])
    work_dir = Path(os.environ["C3_WORK_DIR"])
    output_dir = Path(os.environ["C3_OUTPUT_DIR"])

    from subtap.schemas.config import SubtapConfig
    from subtap.core.tracked_pipeline import TrackedPipeline
    from subtap.ui.tui import RichRunner

    config = SubtapConfig()
    pipeline = TrackedPipeline(config, work_dir=work_dir)
    pipeline.workspace.ensure_dirs()

    runner = RichRunner()
    runner.run_pipeline(
        pipeline,
        input_path,
        output_dir,
        fmt="srt",
        enhance="local",
    )


if __name__ == "__main__":
    main()
