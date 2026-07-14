"""纯本地文稿匹配测试"""


class TestLocalScriptMatch:
    """纯本地文稿匹配测试"""

    def test_script_match_txt(self, workspace, local_config, tmp_path):
        """测试 TXT 文稿匹配"""
        from subtap.script.match import match_from_file

        # 创建文稿文件
        script_path = tmp_path / "script.txt"
        script_path.write_text("测试文本第一句\n测试文本第二句")

        # 创建 ASR 结果
        segments = [
            {
                "sentence_id": 0,
                "chunk_id": 0,
                "start_sec": 0.0,
                "end_sec": 1.5,
                "text": "测试文本第一句",
                "source_text": "测试文本第一句",
            },
            {
                "sentence_id": 1,
                "chunk_id": 0,
                "start_sec": 1.5,
                "end_sec": 3.0,
                "text": "测试文本第二句",
                "source_text": "测试文本第二句",
            },
        ]

        result, report = match_from_file(segments, script_path, mode="follow_script")

        # 验证匹配结果
        assert report.matched >= 0
        assert len(result) == len(segments)

    def test_script_match_srt(self, workspace, local_config, tmp_path):
        """测试 SRT 文稿匹配"""
        from subtap.script.match import match_from_file

        # 创建 SRT 文稿
        srt_content = """1
00:00:00,000 --> 00:00:01,500
测试文本第一句

2
00:00:01,500 --> 00:00:03,000
测试文本第二句"""
        script_path = tmp_path / "script.srt"
        script_path.write_text(srt_content)

        segments = [
            {
                "sentence_id": 0,
                "chunk_id": 0,
                "start_sec": 0.0,
                "end_sec": 1.5,
                "text": "测试文本第一句",
                "source_text": "测试文本第一句",
            },
        ]

        result, report = match_from_file(segments, script_path, mode="follow_script")
        assert len(result) > 0
