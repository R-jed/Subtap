"""纯本地工况端到端测试"""

import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestLocalOnlyPipeline:
    """纯本地工况端到端测试"""

    def test_full_pipeline_local_only(self, sample_audio, workspace, local_config):
        """测试完整本地流水线（无 LLM）"""
        from subtap.core.pipeline import Pipeline
        from subtap.schemas.models import ASRSegment, AlignedSegment

        # 确保禁用 LLM
        local_config.llm_proofread = False
        local_config.llm_hotword = False
        local_config.translate_to = ""

        # Mock ASR 和 Align 后端
        mock_asr = MagicMock()
        mock_asr.transcribe.return_value = [
            ASRSegment(
                chunk_id=0, segment_id=0,
                start_sec=0.0, end_sec=1.5,
                text="测试文本第一句", confidence=0.95,
            ),
        ]
        mock_asr.release_model = MagicMock()

        mock_align = MagicMock()
        mock_align.align.return_value = [
            AlignedSegment(
                sentence_id=0,
                start_sec=0.0, end_sec=1.5,
                text="测试文本第一句",
                words=[{"word": "测试文本第一句", "start_sec": 0.0, "end_sec": 1.5}],
            ),
        ]
        mock_align.release_model = MagicMock()

        pipeline = Pipeline(local_config, workspace.root)

        # 执行流水线
        with patch("subtap.core.asr.get_backend", return_value=mock_asr), \
             patch("subtap.core.align.get_aligner_backend", return_value=mock_align):

            # prepare
            pipeline.run_stage("prepare", input_path=sample_audio)

            # chunk
            pipeline.run_stage("chunk")

            # asr
            pipeline.run_stage("asr", backend_name="mock-asr")

            # clean (本地模式)
            pipeline.run_stage("clean", enhance_mode="off")

            # segment
            pipeline.run_stage("segment")

            # align
            pipeline.run_stage("align", backend_name="mock-align")

            # export
            result = pipeline.run_stage("export", fmt="srt", stem="output")

        # 验证最终输出
        assert "output_path" in result
        assert Path(result["output_path"]).exists()

    def test_pipeline_skip_translate(self, workspace, local_config):
        """测试跳过翻译阶段"""
        from subtap.core.pipeline import Pipeline

        local_config.translate_to = ""
        pipeline = Pipeline(local_config, workspace.root)

        # translate 阶段应该被跳过或报错
        with pytest.raises(ValueError, match="target_language required"):
            pipeline.run_stage("translate")

    def test_pipeline_events_published(self, sample_audio, workspace, local_config):
        """测试流水线事件发布"""
        from subtap.core.pipeline import Pipeline
        from subtap.metrics.events import EventBus, EventType

        local_config.llm_proofread = False
        local_config.llm_hotword = False

        event_bus = EventBus()
        events_received = []

        def handler(event):
            events_received.append(event)

        # 订阅所有事件类型
        for event_type in EventType:
            event_bus.subscribe(event_type, handler)

        pipeline = Pipeline(local_config, workspace.root, event_bus=event_bus)

        with patch("subtap.core.asr.get_backend") as mock_asr_cls, \
             patch("subtap.core.align.get_aligner_backend") as mock_align_cls:

            mock_asr = MagicMock()
            mock_asr.transcribe.return_value = []
            mock_asr.release_model = MagicMock()
            mock_asr_cls.return_value = mock_asr

            mock_align = MagicMock()
            mock_align.align.return_value = []
            mock_align.release_model = MagicMock()
            mock_align_cls.return_value = mock_align

            pipeline.run_stage("prepare", input_path=sample_audio)
            pipeline.run_stage("chunk")

        # 验证事件已通过 publish_nowait 发布（同步模式）
        # 检查事件队列是否有事件
        assert not event_bus._queue.empty()
