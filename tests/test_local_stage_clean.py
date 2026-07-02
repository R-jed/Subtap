"""纯本地 clean 阶段测试（本地规则，无 LLM）"""

import pytest
import json


class TestLocalClean:
    """纯本地 clean 阶段测试（本地规则，无 LLM）"""

    def test_clean_local_rules(self, workspace, local_config):
        """测试本地规则清洗"""
        from subtap.core.clean import local_clean_text

        # 测试 Unicode 规范化
        assert local_clean_text("１２３") == "123"

        # 测试重复词去除
        assert local_clean_text("的的的") == "的"

        # 测试空格处理
        assert local_clean_text("  多余  空格  ") == "多余 空格"

    def test_clean_punctuation_toggle(self, workspace, local_config):
        """测试标点开关"""
        from subtap.core.clean import local_clean_text

        # 带标点
        result_with = local_clean_text("你好，世界！", punctuation=True)
        assert "，" in result_with or "！" in result_with

        # 不带标点
        result_without = local_clean_text("你好，世界！", punctuation=False)
        assert "，" not in result_without
        assert "！" not in result_without

    def test_clean_glossary_replacement(self, workspace, local_config):
        """测试术语表替换"""
        from subtap.core.clean import local_clean_text

        glossary = {"错词": "正确词"}
        result = local_clean_text("这是错词", glossary=glossary)
        assert result == "这是正确词"

    def test_run_clean_no_llm(self, workspace, local_config):
        """测试完整 clean 流程（无 LLM）"""
        from subtap.schemas.models import ASRSegment
        from subtap.core.clean import run_clean

        # 写入测试 ASR 数据
        segments = [
            {"chunk_id": 0, "segment_id": 0, "start_sec": 0.0, "end_sec": 1.0, "text": "测试文本"}
        ]
        with open(workspace.asr_jsonl, "w") as f:
            for seg in segments:
                f.write(json.dumps(seg) + "\n")

        # 禁用 LLM
        local_config.llm_proofread = False
        local_config.llm_hotword = False

        result = run_clean(workspace, local_config, enhance_mode="local")

        # 验证输出
        assert workspace.cleaned_jsonl.exists()
        assert result["segment_count"] == 1
