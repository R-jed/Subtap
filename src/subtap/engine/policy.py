"""Execution policy: controls model selection, LLM usage, and alignment precision."""

from __future__ import annotations

import enum


class PolicyMode(enum.Enum):
    """Execution policy modes."""

    LOCAL_ONLY = "local"  # 本地模型，无 LLM，快速对齐
    FAST_MODE = "fast"  # 最小模型，跳过可选阶段
    QUALITY_MODE = "quality"  # 大模型，完整流程，LLM 增强


# Policy configuration
_POLICIES: dict[PolicyMode, dict] = {
    PolicyMode.LOCAL_ONLY: {
        "asr_backend": "mlx-qwen-asr",
        "asr_model": "asr_0.6b",
        "use_llm": False,
        "align_backend": "mlx-qwen-aligner",
        "skip_stages": [],
        "description": "纯本地执行，不依赖外部服务",
    },
    PolicyMode.FAST_MODE: {
        "asr_backend": "mlx-qwen-asr",
        "asr_model": "asr_0.6b",
        "use_llm": False,
        "align_backend": "mlx-qwen-aligner",
        "skip_stages": [],
        "description": "最快速度，使用小模型",
    },
    PolicyMode.QUALITY_MODE: {
        "asr_backend": "mlx-qwen-asr",
        "asr_model": "asr_1.7b",
        "use_llm": True,
        "align_backend": "mlx-qwen-aligner",
        "skip_stages": [],
        "description": "高质量模式，使用大模型，完整流程 + LLM 增强",
    },
}


class ExecutionPolicy:
    """Determines how the pipeline executes based on user preference."""

    def __init__(self, mode: str = "local"):
        try:
            self.mode = PolicyMode(mode)
        except ValueError:
            self.mode = PolicyMode.LOCAL_ONLY
        self._config = _POLICIES[self.mode]

    @property
    def asr_backend(self) -> str:
        return self._config["asr_backend"]

    @property
    def asr_model(self) -> str:
        return self._config["asr_model"]

    @property
    def use_llm(self) -> bool:
        return self._config["use_llm"]

    @property
    def align_backend(self) -> str:
        return self._config["align_backend"]

    @property
    def skip_stages(self) -> list[str]:
        return self._config["skip_stages"]

    @property
    def description(self) -> str:
        return self._config["description"]

    def should_skip(self, stage: str) -> bool:
        return stage in self.skip_stages

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "asr_backend": self.asr_backend,
            "use_llm": self.use_llm,
            "skip_stages": self.skip_stages,
            "description": self.description,
        }
