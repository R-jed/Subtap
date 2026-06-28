"""Phase 26: import corrected SRT."""

from subtap.learning.importer import parse_srt_text, import_corrected_srt


def test_import_corrected_srt_parses_text_blocks(tmp_path):
    """Corrected SRT import should produce ordered subtitle texts."""
    srt = tmp_path / "corrected.srt"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\n第一句\n\n"
        "2\n00:00:01,000 --> 00:00:02,000\n第二句\n",
        encoding="utf-8",
    )

    assert parse_srt_text(srt.read_text(encoding="utf-8")) == ["第一句", "第二句"]
    assert import_corrected_srt(srt) == ["第一句", "第二句"]
