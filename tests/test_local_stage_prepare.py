"""纯本地 prepare 阶段测试"""

import pytest
from pathlib import Path


class TestLocalPrepare:
    """纯本地 prepare 阶段测试"""

    def test_prepare_extracts_audio(self, sample_audio, workspace, local_config):
        """测试音频提取功能"""
        from subtap.core.media import prepare_media

        result = prepare_media(sample_audio, workspace, local_config)

        # 验证输出文件存在
        assert workspace.source_audio.exists()
        # 验证返回的媒体信息
        assert result.duration > 0
        assert result.sample_rate > 0
        assert result.channels > 0

    def test_prepare_converts_to_wav(self, tmp_path, workspace, local_config):
        """测试非 WAV 格式转换"""
        from pydub import AudioSegment
        from pydub.generators import Sine
        from subtap.core.media import prepare_media

        # 创建 MP3 文件
        audio = Sine(440).to_audio_segment(duration=1000)
        mp3_path = tmp_path / "test.mp3"
        audio.export(str(mp3_path), format="mp3")

        result = prepare_media(mp3_path, workspace, local_config)

        # 验证转换为 WAV
        assert workspace.source_audio.exists()
        assert result.duration > 0

    def test_prepare_rejects_invalid_file(self, tmp_path, workspace, local_config):
        """测试无效文件处理"""
        from subtap.core.media import prepare_media

        # 创建无效文件
        invalid_path = tmp_path / "invalid.txt"
        invalid_path.write_text("not audio")

        with pytest.raises(Exception):
            prepare_media(invalid_path, workspace, local_config)
