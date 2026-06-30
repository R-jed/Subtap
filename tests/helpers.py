"""Shared test helpers and mock backends."""

from __future__ import annotations

import re


class MockLLMBackend:
    """统一的 Mock LLM backend，追踪各方法是否被调用。"""

    def __init__(self):
        self.select_suspicious_segments_called = False
        self.repair_segments_called = False
        self.replace_hotwords_called = False
        self.translate_srt_called = False
        self._selected_ids: list[int] = []

    def select_suspicious_segments(self, segments):
        self.select_suspicious_segments_called = True
        self._selected_ids = [0] if segments else []
        return self._selected_ids

    def repair_segments(self, segments):
        self.repair_segments_called = True
        return {s["i"]: s["t"] + " [fixed]" for s in segments}

    def replace_hotwords(self, segments, hotword_payload):
        self.replace_hotwords_called = True
        return {s["i"]: s["t"] + " [hotword]" for s in segments}

    def translate_srt(self, srt_text, target_language):
        self.translate_srt_called = True
        # 非序号行、非时间码行、非空行，加上翻译前缀
        return re.sub(
            r"^(?!\d+$)(?!.+-->)(.+)$",
            r"[translated] \1",
            srt_text.strip(),
            flags=re.MULTILINE,
        )
