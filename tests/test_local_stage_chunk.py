"""纯本地 chunk 阶段测试"""

import json


class TestLocalChunk:
    """纯本地 chunk 阶段测试"""

    def test_chunk_splits_audio(self, sample_audio, workspace, local_config):
        """测试音频分割功能"""
        from subtap.core.media import prepare_media
        from subtap.core.vad import split_chunks

        # 先准备音频
        prepare_media(sample_audio, workspace, local_config)

        # 执行分割
        chunks = split_chunks(workspace, local_config)

        # 验证分割结果
        assert len(chunks) > 0
        assert workspace.chunks_jsonl.exists()

        # 验证 JSONL 格式
        with open(workspace.chunks_jsonl) as f:
            for line in f:
                chunk = json.loads(line)
                assert "chunk_id" in chunk
                assert "start_sec" in chunk
                assert "end_sec" in chunk
                assert "path" in chunk

    def test_chunk_creates_wav_files(self, sample_audio, workspace, local_config):
        """测试分割后 WAV 文件创建"""
        from subtap.core.media import prepare_media
        from subtap.core.vad import split_chunks

        prepare_media(sample_audio, workspace, local_config)
        chunks = split_chunks(workspace, local_config)

        # 验证每个 chunk 文件存在
        for chunk in chunks:
            chunk_path = workspace.root / chunk.path
            assert chunk_path.exists()
            assert chunk_path.stat().st_size > 0

    def test_chunk_timing_continuity(self, sample_audio, workspace, local_config):
        """测试分割时间连续性"""
        from subtap.core.media import prepare_media
        from subtap.core.vad import split_chunks

        prepare_media(sample_audio, workspace, local_config)
        chunks = split_chunks(workspace, local_config)

        # 验证时间连续性
        for i in range(len(chunks) - 1):
            assert chunks[i].end_sec <= chunks[i + 1].start_sec + 0.1
