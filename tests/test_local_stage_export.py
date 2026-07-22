"""纯本地 export 阶段测试"""

import json
from pathlib import Path


class TestLocalExport:
    """纯本地 export 阶段测试"""

    def test_export_srt(self, workspace, local_config, tmp_path):
        """测试 SRT 导出"""
        from subtap.core.export import run_export

        # 写入测试 aligned 数据
        segments = [
            {
                "sentence_id": 0,
                "start_sec": 0.0,
                "end_sec": 1.5,
                "text": "测试文本第一句",
                "words": [],
            },
            {
                "sentence_id": 1,
                "start_sec": 1.5,
                "end_sec": 3.0,
                "text": "测试文本第二句",
                "words": [],
            },
        ]
        with open(workspace.aligned_jsonl, "w") as f:
            for seg in segments:
                f.write(json.dumps(seg) + "\n")

        output_dir = tmp_path / "output"
        result = run_export(
            workspace.aligned_jsonl,
            output_dir,
            fmt="srt",
            stem="test",
            max_chars=25,
            punctuation=False,
            language="zh",
        )

        # 验证输出文件
        output_path = Path(result["output_path"])
        assert output_path.exists()
        assert output_path.suffix == ".srt"

        # 验证 SRT 格式
        content = output_path.read_text()
        assert "00:00:00,000 --> 00:00:01,500" in content
        assert "测试文本第一句" in content

    def test_export_txt(self, workspace, local_config, tmp_path):
        """测试 TXT 导出"""
        from subtap.core.export import run_export

        segments = [
            {
                "sentence_id": 0,
                "start_sec": 0.0,
                "end_sec": 1.5,
                "text": "测试文本",
                "words": [],
            },
        ]
        with open(workspace.aligned_jsonl, "w") as f:
            for seg in segments:
                f.write(json.dumps(seg) + "\n")

        output_dir = tmp_path / "output"
        result = run_export(
            workspace.aligned_jsonl,
            output_dir,
            fmt="txt",
            stem="test",
            max_chars=25,
            punctuation=False,
            language="zh",
        )

        output_path = Path(result["output_path"])
        assert output_path.exists()
        assert output_path.suffix == ".txt"

    def test_export_ass(self, workspace, local_config, tmp_path):
        """测试 ASS 导出"""
        from subtap.core.export import run_export

        segments = [
            {
                "sentence_id": 0,
                "start_sec": 0.0,
                "end_sec": 1.5,
                "text": "测试文本",
                "words": [],
            },
        ]
        with open(workspace.aligned_jsonl, "w") as f:
            for seg in segments:
                f.write(json.dumps(seg) + "\n")

        output_dir = tmp_path / "output"
        result = run_export(
            workspace.aligned_jsonl,
            output_dir,
            fmt="ass",
            stem="test",
            max_chars=25,
            punctuation=False,
            language="zh",
        )

        output_path = Path(result["output_path"])
        assert output_path.exists()
        assert output_path.suffix == ".ass"
