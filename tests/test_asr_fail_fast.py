"""ASR backend fail-fast behavior."""

from __future__ import annotations

import pytest

from subtap.backends.asr.mlx_qwen_asr import MLXQwenASR
from subtap.schemas.config import ASRConfig
from subtap.schemas.models import Chunk


def test_mlx_asr_missing_chunk_fails_fast(tmp_path):
    backend = MLXQwenASR(ASRConfig(), model_root=tmp_path / "models")
    backend._model = object()
    missing = tmp_path / "missing.wav"
    chunk = Chunk(chunk_id=0, start_sec=0.0, end_sec=1.0, path=str(missing))

    with pytest.raises(FileNotFoundError, match="ASR chunk file not found"):
        backend.transcribe([chunk])


def test_mlx_asr_limits_generation_by_chunk_duration(tmp_path, monkeypatch):
    """Short speech chunks must not inherit the runtime's 8192-token ceiling."""
    import mlx_audio.stt.generate as generate_module

    captured = {}

    def fake_generate_transcription(**kwargs):
        captured.update(kwargs)
        return {"text": "测试"}

    monkeypatch.setattr(
        generate_module, "generate_transcription", fake_generate_transcription
    )
    audio = tmp_path / "chunk.wav"
    audio.write_bytes(b"RIFF")
    backend = MLXQwenASR(ASRConfig(), model_root=tmp_path / "models")
    backend._model = object()
    chunk = Chunk(chunk_id=0, start_sec=10.0, end_sec=24.5, path=str(audio))

    backend.transcribe([chunk])

    assert captured["max_tokens"] == 296


def test_mlx_asr_retries_without_hotwords_when_model_echoes_prompt(
    tmp_path, monkeypatch
):
    """A model protocol echo is not an audio transcription."""
    import mlx_audio.stt.generate as generate_module

    calls = []

    def fake_generate_transcription(**kwargs):
        calls.append(kwargs)
        if "system_prompt" in kwargs:
            return {"text": "请注意以下专业术语和人名：模型重排后的术语。"}
        return {"text": "真正内容"}

    monkeypatch.setattr(
        generate_module, "generate_transcription", fake_generate_transcription
    )
    audio = tmp_path / "chunk.wav"
    audio.write_bytes(b"RIFF")
    backend = MLXQwenASR(ASRConfig(), model_root=tmp_path / "models")
    backend._model = object()
    chunk = Chunk(chunk_id=0, start_sec=0.0, end_sec=2.0, path=str(audio))

    segments = backend.transcribe([chunk], hotwords=["术语"])

    assert len(calls) == 2
    assert "system_prompt" in calls[0]
    assert "system_prompt" not in calls[1]
    assert segments[0].text == "真正内容"


def test_mlx_asr_retries_runaway_repetition(tmp_path, monkeypatch):
    """Decoder loops must be retried instead of reaching alignment."""
    import mlx_audio.stt.generate as generate_module

    calls = []

    def fake_generate_transcription(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return {"text": "嗯，" * 20}
        return {"text": "恢复后的内容"}

    monkeypatch.setattr(
        generate_module, "generate_transcription", fake_generate_transcription
    )
    audio = tmp_path / "chunk.wav"
    audio.write_bytes(b"RIFF")
    backend = MLXQwenASR(ASRConfig(), model_root=tmp_path / "models")
    backend._model = object()
    chunk = Chunk(chunk_id=0, start_sec=0.0, end_sec=2.0, path=str(audio))

    segments = backend.transcribe([chunk], hotwords=["术语"])

    assert len(calls) == 2
    assert segments[0].text == "恢复后的内容"


def test_mlx_asr_rejects_prompt_echo_after_retry(tmp_path, monkeypatch):
    """A retry must pass the same protocol checks as the first generation."""
    import mlx_audio.stt.generate as generate_module

    monkeypatch.setattr(
        generate_module,
        "generate_transcription",
        lambda **kwargs: {"text": "请注意以下专业术语和人名：仍在回显。"},
    )
    audio = tmp_path / "chunk.wav"
    audio.write_bytes(b"RIFF")
    backend = MLXQwenASR(ASRConfig(), model_root=tmp_path / "models")
    backend._model = object()
    chunk = Chunk(chunk_id=0, start_sec=0.0, end_sec=2.0, path=str(audio))

    with pytest.raises(RuntimeError, match="hotword prompt persisted"):
        backend.transcribe([chunk], hotwords=["术语"])


@pytest.mark.parametrize("runtime_result", [object(), {}, {"segments": [{}]}])
def test_mlx_asr_rejects_unknown_runtime_result(tmp_path, monkeypatch, runtime_result):
    """An incompatible runtime response is not a silent empty transcript."""
    import mlx_audio.stt.generate as generate_module

    monkeypatch.setattr(
        generate_module,
        "generate_transcription",
        lambda **kwargs: runtime_result,
    )
    audio = tmp_path / "chunk.wav"
    audio.write_bytes(b"RIFF")
    backend = MLXQwenASR(ASRConfig(), model_root=tmp_path / "models")
    backend._model = object()
    chunk = Chunk(chunk_id=0, start_sec=0.0, end_sec=2.0, path=str(audio))

    with pytest.raises(RuntimeError, match="unsupported result type"):
        backend.transcribe([chunk])


def test_mlx_asr_uses_segments_when_top_level_text_is_empty(tmp_path, monkeypatch):
    """A valid segmented result must not be hidden by an empty summary field."""
    import mlx_audio.stt.generate as generate_module

    monkeypatch.setattr(
        generate_module,
        "generate_transcription",
        lambda **kwargs: {
            "text": "",
            "segments": [{"text": "第一段"}, {"text": "第二段"}],
        },
    )
    audio = tmp_path / "chunk.wav"
    audio.write_bytes(b"RIFF")
    backend = MLXQwenASR(ASRConfig(), model_root=tmp_path / "models")
    backend._model = object()
    chunk = Chunk(chunk_id=0, start_sec=0.0, end_sec=2.0, path=str(audio))

    segments = backend.transcribe([chunk])

    assert segments[0].text == "第一段 第二段"
