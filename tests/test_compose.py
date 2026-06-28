"""Tests for subtitle burn-in compose commands."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from subtap.cli import app
from subtap.compose import build_burn_subtitle_command, compose_batch, compose_one

runner = CliRunner()


def test_build_burn_subtitle_command_uses_ffmpeg_subtitles_filter(tmp_path):
    video = tmp_path / "demo.mp4"
    subtitle = tmp_path / "final.srt"
    output = tmp_path / "out.mp4"

    command = build_burn_subtitle_command(video, subtitle, output, ffmpeg="ffmpeg")

    assert command[:2] == ["ffmpeg", "-y"]
    assert str(video) in command
    assert any("subtitles=" in item and str(subtitle) in item for item in command)
    assert command[-1] == str(output)


def test_compose_one_rejects_audio_file(tmp_path):
    audio = tmp_path / "demo.mp3"
    subtitle = tmp_path / "final.srt"
    output = tmp_path / "out.mp4"
    audio.write_bytes(b"audio")
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")

    result = compose_one(audio, subtitle, output)

    assert result["status"] == "skipped"
    assert result["error"] == "不是视频文件"


def test_compose_one_runs_ffmpeg_with_mock_runner(tmp_path):
    calls = []
    video = tmp_path / "demo.mp4"
    subtitle = tmp_path / "final.srt"
    output = tmp_path / "out.mp4"
    video.write_bytes(b"video")
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")

    def runner(command):
        calls.append(command)
        output.write_bytes(b"out")

    result = compose_one(video, subtitle, output, runner=runner, ffmpeg="ffmpeg")

    assert result["status"] == "succeeded"
    assert calls
    assert output.exists()


def test_compose_batch_writes_manifest_and_skips_missing_subtitle(tmp_path):
    video = tmp_path / "demo.mp4"
    missing_subtitle = tmp_path / "missing.srt"
    out_dir = tmp_path / "out"
    video.write_bytes(b"video")

    manifest = compose_batch(
        [{"video": video, "subtitle": missing_subtitle}],
        out_dir,
        runner=lambda _command: None,
    )

    saved = json.loads((out_dir / "compose-manifest.json").read_text(encoding="utf-8"))
    assert manifest["items"][0]["status"] == "failed"
    assert saved["items"][0]["error"] == "字幕文件不存在"


def test_compose_cli_reports_output(tmp_path, monkeypatch):
    video = tmp_path / "demo.mp4"
    subtitle = tmp_path / "final.srt"
    output = tmp_path / "out.mp4"
    video.write_bytes(b"video")
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")

    monkeypatch.setattr("subtap.compose.run_command", lambda command: output.write_bytes(b"out"))

    result = runner.invoke(
        app,
        ["compose", str(video), "--subtitle", str(subtitle), "--output", str(output)],
    )

    assert result.exit_code == 0
    assert "合成完成" in result.output
