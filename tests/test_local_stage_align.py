"""纯本地 align 阶段测试（Mock 后端）"""

import pytest
import json
from unittest.mock import patch, MagicMock


class TestLocalAlign:
    """纯本地 align 阶段测试（Mock 后端）"""

    @pytest.fixture
    def mock_align_backend(self):
        """Mock 对齐后端"""
        from subtap.schemas.models import AlignedSegment

        mock = MagicMock()
        mock.align.return_value = [
            AlignedSegment(
                sentence_id=0,
                start_sec=0.0,
                end_sec=1.5,
                text="测试文本第一句",
                words=[
                    {"word": "测试", "start_sec": 0.0, "end_sec": 0.5},
                    {"word": "文本", "start_sec": 0.5, "end_sec": 1.0},
                    {"word": "第一句", "start_sec": 1.0, "end_sec": 1.5},
                ],
            ),
        ]
        return mock

    def test_align_writes_jsonl(self, workspace, local_config, mock_align_backend):
        """测试对齐输出 JSONL 格式"""
        from subtap.core.align import run_align

        # 写入测试 sentences 数据
        sentences = [
            {"sentence_id": 0, "chunk_id": 0, "start_sec": 0.0, "end_sec": 1.5, "text": "测试文本第一句", "source_text": "测试文本第一句"},
        ]
        with open(workspace.sentences_jsonl, "w") as f:
            for sent in sentences:
                f.write(json.dumps(sent) + "\n")

        # Mock 对齐后端
        with patch("subtap.core.align.get_aligner_backend", return_value=mock_align_backend):
            result = run_align(workspace, local_config)

        # 验证输出
        assert workspace.aligned_jsonl.exists()
        assert result["aligned_count"] == 1

        # 验证 JSONL 内容
        with open(workspace.aligned_jsonl) as f:
            seg = json.loads(f.readline())
            assert "start_sec" in seg
            assert "end_sec" in seg
            assert "words" in seg

    def test_align_fixes_word_timing(self, workspace, local_config):
        """测试词级时间戳修复"""
        from subtap.core.align import run_align
        from subtap.schemas.models import AlignedSegment

        # 创建有问题的时间戳
        mock_backend = MagicMock()
        mock_backend.align.return_value = [
            AlignedSegment(
                sentence_id=0,
                start_sec=0.0,
                end_sec=1.0,
                text="测试",
                words=[
                    {"word": "测", "start_sec": 0.0, "end_sec": 0.0},  # 零时长
                    {"word": "试", "start_sec": 0.0, "end_sec": 1.0},  # 重叠
                ],
            ),
        ]

        sentences = [
            {"sentence_id": 0, "chunk_id": 0, "start_sec": 0.0, "end_sec": 1.0, "text": "测试", "source_text": "测试"},
        ]
        with open(workspace.sentences_jsonl, "w") as f:
            for sent in sentences:
                f.write(json.dumps(sent) + "\n")

        with patch("subtap.core.align.get_aligner_backend", return_value=mock_backend):
            run_align(workspace, local_config)

        # 验证时间戳修复
        with open(workspace.aligned_jsonl) as f:
            seg = json.loads(f.readline())
            words = seg["words"]
            # 零时长应被修复
            assert words[0]["end_sec"] > words[0]["start_sec"]
