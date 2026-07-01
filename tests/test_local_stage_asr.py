"""纯本地 ASR 阶段测试（Mock 后端）"""

import pytest
import json
from unittest.mock import patch, MagicMock


class TestLocalASR:
    """纯本地 ASR 阶段测试（Mock 后端）"""

    @pytest.fixture
    def mock_asr_backend(self):
        """Mock ASR 后端"""
        from subtap.schemas.models import ASRSegment

        mock = MagicMock()
        mock.transcribe.return_value = [
            ASRSegment(
                chunk_id=0,
                segment_id=0,
                start_sec=0.0,
                end_sec=1.5,
                text="测试文本",
                confidence=0.95,
            ),
            ASRSegment(
                chunk_id=0,
                segment_id=1,
                start_sec=1.5,
                end_sec=3.0,
                text="第二句",
                confidence=0.90,
            ),
        ]
        return mock

    def test_asr_writes_jsonl(self, sample_audio, workspace, local_config, mock_asr_backend):
        """测试 ASR 输出 JSONL 格式"""
        from subtap.core.media import prepare_media
        from subtap.core.vad import split_chunks
        from subtap.core.asr import run_asr

        # 准备数据
        prepare_media(sample_audio, workspace, local_config)
        split_chunks(workspace, local_config)

        # Mock ASR 后端
        with patch("subtap.core.asr.get_backend", return_value=mock_asr_backend):
            result = run_asr(workspace, local_config)

        # 验证输出
        assert workspace.asr_jsonl.exists()
        assert result["segment_count"] == 2

        # 验证 JSONL 内容
        with open(workspace.asr_jsonl) as f:
            lines = f.readlines()
            assert len(lines) == 2
            seg = json.loads(lines[0])
            assert seg["text"] == "测试文本"

    def test_asr_creates_draft(self, sample_audio, workspace, local_config, mock_asr_backend):
        """测试 ASR 草稿文件创建"""
        from subtap.core.media import prepare_media
        from subtap.core.vad import split_chunks
        from subtap.core.asr import run_asr

        prepare_media(sample_audio, workspace, local_config)
        split_chunks(workspace, local_config)

        with patch("subtap.core.asr.get_backend", return_value=mock_asr_backend):
            run_asr(workspace, local_config)

        # 验证草稿文件
        assert workspace.asr_draft_jsonl.exists()
