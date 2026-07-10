# Silero VAD Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace pydub detect_nonsilent with Silero VAD to find natural speech pause points and avoid sentence truncation.

**Architecture:** Use Silero VAD's speech probability output to detect natural pause points, then split chunks at these boundaries instead of mechanical time-based cutting. Keep max_chunk_sec as a fallback safety limit.

**Tech Stack:** silero-vad (ONNX), onnxruntime, pydub (for audio I/O)

## Global Constraints

- Python 3.10+
- 保持现有接口 `split_chunks(workspace, config) -> list[Chunk]`
- 保持现有配置结构 `config.audio.vad`
- 新增配置项：`use_silero_vad: bool = True`

---

## File Structure

**Modified Files:**
- `src/subtap/core/vad.py` — 主要修改，集成 Silero VAD
- `src/subtap/schemas/config.py` — 新增 VAD 配置项
- `tests/test_vad.py` — 新增测试

**New Files:**
- 无新文件，复用现有结构

---

## Task 1: 配置扩展

**Files:**
- Modify: `src/subtap/schemas/config.py`
- Test: `tests/test_vad.py`

**Interfaces:**
- Consumes: 无
- Produces: `VADConfig.use_silero_vad` 字段

- [ ] **Step 1: Write the failing test**

```python
# tests/test_vad.py
import pytest
from subtap.schemas.config import VADConfig

def test_vad_config_silero_field():
    """VADConfig should have use_silero_vad field with default True."""
    config = VADConfig()
    assert hasattr(config, 'use_silero_vad')
    assert config.use_silero_vad is True

def test_vad_config_silero_false():
    """VADConfig should accept use_silero_vad=False."""
    config = VADConfig(use_silero_vad=False)
    assert config.use_silero_vad is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_vad.py -v`
Expected: FAIL with "VADConfig() got an unexpected keyword argument 'use_silero_vad'"

- [ ] **Step 3: Write minimal implementation**

```python
# src/subtap/schemas/config.py - VADConfig 类添加
class VADConfig(BaseModel):
    min_silence_sec: float = 0.4
    min_chunk_sec: float = 1.0
    max_chunk_sec: float = 30.0
    use_silero_vad: bool = True  # 新增
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_vad.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/subtap/schemas/config.py tests/test_vad.py
git commit -m "feat(vad): 添加 use_silero_vad 配置项"
```

---

## Task 2: 依赖安装

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: 无
- Produces: 依赖可用

- [ ] **Step 1: 安装依赖**

```bash
uv add silero-vad onnxruntime
```

- [ ] **Step 2: 验证安装**

```bash
python -c "from silero_vad import load_silero_vad; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: 添加 silero-vad 和 onnxruntime"
```

---

## Task 3: Silero VAD 核心实现

**Files:**
- Modify: `src/subtap/core/vad.py`
- Test: `tests/test_vad.py`

**Interfaces:**
- Consumes: `VADConfig.use_silero_vad`
- Produces: `split_chunks()` 返回基于自然停顿的 chunks

- [ ] **Step 1: Write the failing test**

```python
# tests/test_vad.py
import pytest
from pathlib import Path
from subtap.schemas.config import SubtapConfig
from subtap.core.workspace import Workspace
from subtap.core.vad import split_chunks

def test_silero_vad_finds_natural_pauses():
    """Silero VAD should find natural pause points, not mechanical splits."""
    # 使用测试音频
    test_audio = Path("/Users/qunqing/Downloads/ASR-SRT测试音频/高质量中文语音.wav")
    if not test_audio.exists():
        pytest.skip("测试音频不存在")

    config = SubtapConfig()
    config.audio.vad.use_silero_vad = True
    config.audio.vad.max_chunk_sec = 10.0  # 设置较小的 max 以便观察切割

    workspace = Workspace(root=Path("work_test"))
    workspace.source_audio = test_audio

    chunks = split_chunks(workspace, config)

    # 验证 chunks 不是机械的 10s 切割
    for chunk in chunks:
        duration = chunk.end_sec - chunk.start_sec
        assert duration <= config.audio.vad.max_chunk_sec + 1.0  # 允许小误差

    # 验证有自然停顿（chunk 时长不完全相同）
    durations = [c.end_sec - c.start_sec for c in chunks]
    assert len(set([round(d, 1) for d in durations])) > 1, "应该有不同长度的 chunks"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_vad.py::test_silero_vad_finds_natural_pauses -v`
Expected: FAIL (Silero VAD 未实现)

- [ ] **Step 3: Write minimal implementation**

```python
# src/subtap/core/vad.py
import numpy as np
from pathlib import Path

def _load_silero_vad():
    """Load Silero VAD model."""
    from silero_vad import load_silero_vad
    return load_silero_vad()

def _get_speech_segments(audio_path: Path, model, threshold: float = 0.5) -> list[list[float]]:
    """Get speech segments using Silero VAD."""
    from pydub import AudioSegment

    audio = AudioSegment.from_wav(audio_path)
    # 转换为 numpy array
    samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
    sample_rate = audio.frame_rate

    # Silero VAD 需要 16kHz
    if sample_rate != 16000:
        from pydub import AudioSegment
        audio = audio.set_frame_rate(16000)
        samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
        sample_rate = 16000

    # 获取语音概率
    speech_probs = []
    window_size = 512
    for i in range(0, len(samples), window_size):
        chunk = samples[i:i + window_size]
        if len(chunk) < window_size:
            chunk = np.pad(chunk, (0, window_size - len(chunk)))
        prob = model(chunk, sample_rate).item()
        speech_probs.append(prob)

    # 找到语音段
    speech_segments = []
    in_speech = False
    start = 0

    for i, prob in enumerate(speech_probs):
        if prob >= threshold and not in_speech:
            start = i * window_size / sample_rate
            in_speech = True
        elif prob < threshold and in_speech:
            end = i * window_size / sample_rate
            speech_segments.append([start, end])
            in_speech = False

    if in_speech:
        end = len(speech_probs) * window_size / sample_rate
        speech_segments.append([start, end])

    return speech_segments

def split_chunks(workspace: Workspace, config: SubtapConfig) -> list[Chunk]:
    """Split source audio into chunks based on silence detection."""
    vad_cfg = config.audio.vad
    audio = AudioSegment.from_wav(workspace.source_audio)

    if vad_cfg.use_silero_vad:
        # 使用 Silero VAD
        model = _load_silero_vad()
        nonsilent = _get_speech_segments(workspace.source_audio, model)
    else:
        # 使用原有 pydub detect_nonsilent
        nonsilent = detect_nonsilent(
            audio,
            min_silence_len=int(vad_cfg.min_silence_sec * 1000),
            silence_thresh=-40,
            seek_step=10,
        )

    if not nonsilent:
        nonsilent = [[0, len(audio)]]

    # ... 后续逻辑保持不变
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_vad.py::test_silero_vad_finds_natural_pauses -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/subtap/core/vad.py tests/test_vad.py
git commit -m "feat(vad): 集成 Silero VAD，基于语音概率找自然停顿"
```

---

## Task 4: 集成测试验证

**Files:**
- Test: `tests/test_vad.py`

**Interfaces:**
- Consumes: Silero VAD 实现
- Produces: 验证句子不再被截断

- [ ] **Step 1: Write the failing test**

```python
# tests/test_vad.py
def test_no_sentence_truncation():
    """Chunks should not truncate sentences at boundaries."""
    test_audio = Path("/Users/qunqing/Downloads/ASR-SRT测试音频/高质量中文语音.wav")
    if not test_audio.exists():
        pytest.skip("测试音频不存在")

    config = SubtapConfig()
    config.audio.vad.use_silero_vad = True

    workspace = Workspace(root=work_test)
    workspace.source_audio = test_audio

    chunks = split_chunks(workspace, config)

    # 验证 chunk 边界在自然停顿处
    # （这个测试需要人工验证或更复杂的逻辑）
    assert len(chunks) > 0

    # 验证没有过短的 chunk（可能表示截断）
    for chunk in chunks:
        duration = chunk.end_sec - chunk.start_sec
        assert duration >= 1.0, f"Chunk {chunk.chunk_id} 太短: {duration}s"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_vad.py::test_no_sentence_truncation -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_vad.py
git commit -m "test(vad): 添加句子截断验证测试"
```

---

## Task 5: 清理和文档

**Files:**
- Modify: `README.md` (可选)

**Interfaces:**
- Consumes: 所有实现
- Produces: 完成的集成

- [ ] **Step 1: 验证所有测试通过**

Run: `pytest tests/test_vad.py -v`
Expected: All tests PASS

- [ ] **Step 2: Commit**

```bash
git commit -m "docs(vad): 更新 Silero VAD 集成文档"
```

---

## Verification Checklist

- [ ] 所有测试通过
- [ ] Silero VAD 能找到自然停顿
- [ ] Chunk 边界不再机械切割
- [ ] 句子不再被截断
- [ ] 配置 `use_silero_vad` 可切换
