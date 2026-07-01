"""纯本地 segment 阶段测试"""

import pytest
import json


class TestLocalSegment:
    """纯本地 segment 阶段测试"""

    def test_segment_creates_sentences(self, workspace, local_config):
        """测试断句功能"""
        from subtap.core.segment import run_segment

        # 写入测试 cleaned 数据
        segments = [
            {"segment_id": 0, "source_chunk_id": 0, "original_text": "测试", "cleaned_text": "测试文本第一句"},
            {"segment_id": 1, "source_chunk_id": 0, "original_text": "第二", "cleaned_text": "测试文本第二句"},
        ]
        with open(workspace.cleaned_jsonl, "w") as f:
            for seg in segments:
                f.write(json.dumps(seg) + "\n")

        result = run_segment(workspace, 0.0, 1.0)

        # 验证输出
        assert workspace.sentences_jsonl.exists()
        assert result["sentence_count"] > 0

    def test_segment_preserves_timing(self, workspace, local_config):
        """测试时间戳保持"""
        from subtap.core.segment import run_segment

        # 写入带时间的测试数据
        segments = [
            {"segment_id": 0, "source_chunk_id": 0, "original_text": "测试", "cleaned_text": "测试文本"},
        ]
        with open(workspace.cleaned_jsonl, "w") as f:
            for seg in segments:
                f.write(json.dumps(seg) + "\n")

        run_segment(workspace, 0.0, 3.0)

        # 验证时间戳
        with open(workspace.sentences_jsonl) as f:
            for line in f:
                sent = json.loads(line)
                assert "start_sec" in sent
                assert "end_sec" in sent
                assert sent["start_sec"] < sent["end_sec"]
