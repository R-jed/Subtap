"""Stage state machine for pipeline execution."""

from __future__ import annotations

import enum
import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# Persisted state schema version
STATE_VERSION = 2


class StageStatus(enum.Enum):
    """State of a single pipeline stage."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"


# Chinese labels for status display
STATUS_CN: dict[StageStatus, str] = {
    StageStatus.PENDING: "等待中",
    StageStatus.RUNNING: "执行中",
    StageStatus.SUCCESS: "已完成",
    StageStatus.FAILED: "失败",
    StageStatus.RETRYING: "重试中",
    StageStatus.SKIPPED: "已跳过",
}


@dataclass
class StageState:
    """State of a single pipeline stage with retry tracking."""

    name: str
    name_cn: str
    status: StageStatus = StageStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    error_msg: str = ""
    result: dict = field(default_factory=dict)
    duration_sec: float = 0.0

    @property
    def can_retry(self) -> bool:
        return self.status == StageStatus.FAILED and self.retry_count < self.max_retries

    @property
    def is_terminal(self) -> bool:
        return self.status in (StageStatus.SUCCESS, StageStatus.SKIPPED)

    def transition(self, new_status: StageStatus) -> None:
        """Transition to a new status."""
        self.status = new_status

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "name_cn": self.name_cn,
            "status": self.status.value,
            "retry_count": self.retry_count,
            "error_msg": self.error_msg,
            "duration_sec": round(self.duration_sec, 2),
        }


# Stage name → Chinese mapping (core + optional)
STAGE_CN: dict[str, str] = {
    "prepare": "音频标准化",
    "chunk": "音频切段",
    "asr": "语音识别",
    "clean": "文本清洗",
    "segment": "智能断句",
    "script_match": "文稿匹配",
    "align": "时间轴对齐",
    "hotword": "热词替换",
    "learn": "热词学习",
    "translate": "字幕翻译",
    "export": "字幕导出",
}

STAGE_ORDER = ["prepare", "chunk", "asr", "clean", "segment", "align", "export"]

# Valid statuses for schema validation
_VALID_STATUSES = {s.value for s in StageStatus}


@dataclass(frozen=True)
class PipelineRunContext:
    """Immutable context for a pipeline run.

    Persisted so resume can reconstruct the exact run configuration
    without relying on CLI arguments matching the original run.

    Contains ALL effective values that influence stage behavior:
    CLI overrides + loaded config + defaults → final effective values.
    """

    input_path: str
    output_dir: str
    fmt: str = "srt"
    enhance: str = "local"
    translate_to: str = ""
    bilingual: str = "off"
    script_path: str = ""
    script_mode: str = "follow_script"
    subtitle_language: str = "zh"
    subtitle_punctuation: bool = False
    max_chars: int = 24
    glossary_path: str = ""
    # Effective config values that influence stage behavior
    llm_proofread: bool = False
    llm_hotword: bool = False
    asr_backend: str = "mlx-qwen-asr"
    asr_model: str = "asr_0.6b"
    asr_hotwords: str = ""  # comma-separated
    subtitle_stem: str = "final"
    # Policy
    policy_mode: str = "local"
    local_only: bool = False

    def to_dict(self) -> dict:
        return {
            "input_path": self.input_path,
            "output_dir": self.output_dir,
            "fmt": self.fmt,
            "enhance": self.enhance,
            "translate_to": self.translate_to,
            "bilingual": self.bilingual,
            "script_path": self.script_path,
            "script_mode": self.script_mode,
            "subtitle_language": self.subtitle_language,
            "subtitle_punctuation": self.subtitle_punctuation,
            "max_chars": self.max_chars,
            "glossary_path": self.glossary_path,
            "llm_proofread": self.llm_proofread,
            "llm_hotword": self.llm_hotword,
            "asr_backend": self.asr_backend,
            "asr_model": self.asr_model,
            "asr_hotwords": self.asr_hotwords,
            "subtitle_stem": self.subtitle_stem,
            "policy_mode": self.policy_mode,
            "local_only": self.local_only,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineRunContext":
        return cls(
            input_path=data["input_path"],
            output_dir=data["output_dir"],
            fmt=data.get("fmt", "srt"),
            enhance=data.get("enhance", "local"),
            translate_to=data.get("translate_to", ""),
            bilingual=data.get("bilingual", "off"),
            script_path=data.get("script_path", ""),
            script_mode=data.get("script_mode", "follow_script"),
            subtitle_language=data.get("subtitle_language", "zh"),
            subtitle_punctuation=data.get("subtitle_punctuation", False),
            max_chars=data.get("max_chars", 24),
            glossary_path=data.get("glossary_path", ""),
            llm_proofread=data.get("llm_proofread", False),
            llm_hotword=data.get("llm_hotword", False),
            asr_backend=data.get("asr_backend", "mlx-qwen-asr"),
            asr_model=data.get("asr_model", "asr_0.6b"),
            asr_hotwords=data.get("asr_hotwords", ""),
            subtitle_stem=data.get("subtitle_stem", "final"),
            policy_mode=data.get("policy_mode", "local"),
            local_only=data.get("local_only", False),
        )


def build_stage_kwargs(
    stage_name: str,
    ctx: PipelineRunContext | None,
    config: object | None = None,
) -> dict:
    """Build deterministic kwargs for a stage from persisted context.

    Used by both normal run and resume/retry to ensure identical parameters.
    Returns empty dict when ctx is None (legacy state without context).
    """
    if ctx is None:
        return {}
    if stage_name == "prepare":
        return {"input_path": Path(ctx.input_path)}
    elif stage_name == "chunk":
        return {}
    elif stage_name == "asr":
        kwargs: dict = {}
        if ctx.asr_backend:
            kwargs["backend_name"] = ctx.asr_backend
        return kwargs
    elif stage_name == "clean":
        return {"enhance_mode": ctx.enhance, "glossary_path": ctx.glossary_path or None}
    elif stage_name == "segment":
        return {}
    elif stage_name == "script_match":
        return {}
    elif stage_name == "align":
        kwargs = {}
        if ctx.asr_backend:
            kwargs["backend_name"] = None  # align uses its own backend
        return kwargs
    elif stage_name == "hotword":
        return {"glossary_path": ctx.glossary_path or None}
    elif stage_name == "learn":
        return {"glossary_path": ctx.glossary_path or None}
    elif stage_name == "translate":
        return {"target_language": ctx.translate_to}
    elif stage_name == "export":
        return {
            "fmt": ctx.fmt,
            "output_dir": ctx.output_dir,
            "stem": ctx.subtitle_stem,
            "translate_to": ctx.translate_to or None,
            "bilingual": ctx.bilingual,
        }
    return {}


class PipelineState:
    """Tracks the state of all stages in a pipeline run."""

    def __init__(self, stage_order: list[str] | None = None):
        order = stage_order or STAGE_ORDER
        self.stage_order: list[str] = list(order)
        self.stages: dict[str, StageState] = {
            name: StageState(name=name, name_cn=STAGE_CN.get(name, name))
            for name in self.stage_order
        }
        self.context: PipelineRunContext | None = None
        self._listeners: list = []

    @classmethod
    def new(
        cls,
        stage_order: list[str],
        context: PipelineRunContext | None = None,
    ) -> "PipelineState":
        """Create a fresh state with a dynamic stage plan."""
        state = cls(stage_order=stage_order)
        state.context = context
        return state

    def get(self, stage: str) -> StageState:
        return self.stages[stage]

    @property
    def current_stage(self) -> Optional[str]:
        for name in self.stage_order:
            s = self.stages[name]
            if s.status in (StageStatus.RUNNING, StageStatus.RETRYING):
                return name
        return None

    @property
    def progress_pct(self) -> float:
        completed = sum(1 for s in self.stages.values() if s.is_terminal)
        return completed / len(self.stages) * 100

    @property
    def summary(self) -> dict:
        return {name: s.to_dict() for name, s in self.stages.items()}

    def on_change(self, callback) -> None:
        self._listeners.append(callback)

    def _notify(self, stage: str) -> None:
        for cb in self._listeners:
            try:
                cb(stage, self.stages[stage])
            except Exception as e:
                logger.warning(
                    "Pipeline state listener callback failed for stage %s: %s", stage, e
                )

    def mark_running(self, stage: str) -> None:
        s = self.stages[stage]
        s.transition(StageStatus.RUNNING)
        self._notify(stage)

    def mark_success(self, stage: str, result: dict, duration: float) -> None:
        s = self.stages[stage]
        s.result = result
        s.duration_sec = duration
        s.transition(StageStatus.SUCCESS)
        self._notify(stage)

    def mark_failed(self, stage: str, error: str) -> None:
        s = self.stages[stage]
        s.error_msg = error
        s.transition(StageStatus.FAILED)
        self._notify(stage)

    def mark_retrying(self, stage: str) -> None:
        s = self.stages[stage]
        s.transition(StageStatus.RETRYING)
        self._notify(stage)

    def mark_skipped(self, stage: str) -> None:
        s = self.stages[stage]
        s.transition(StageStatus.SKIPPED)
        self._notify(stage)

    def reset(self, stage: str) -> None:
        self.stages[stage] = StageState(
            name=stage,
            name_cn=STAGE_CN.get(stage, stage),
        )
        self._notify(stage)

    def to_dict(self) -> dict:
        """Serialize state to dict."""
        data: dict = {
            "version": STATE_VERSION,
            "stage_order": self.stage_order,
            "stages": {
                name: {
                    "status": s.status.value,
                    "retry_count": s.retry_count,
                    "max_retries": s.max_retries,
                    "error_msg": s.error_msg,
                    "result": s.result,
                    "duration_sec": s.duration_sec,
                }
                for name, s in self.stages.items()
            },
        }
        if self.context is not None:
            data["context"] = self.context.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineState":
        """Deserialize state from dict.

        Supports v1 (fixed 7-stage) and v2 (dynamic stage_order) formats.
        Unknown versions raise ValueError.
        """
        version = data.get("version", 1)
        if version == 1:
            # v1: fixed 7-stage order, no context
            state = cls()
        elif version == 2:
            if "stage_order" not in data:
                raise ValueError("v2 state missing required 'stage_order' field")
            stage_order = data["stage_order"]
            if not isinstance(stage_order, list) or not stage_order:
                raise ValueError("v2 state 'stage_order' must be a non-empty list")
            if not all(isinstance(s, str) for s in stage_order):
                raise ValueError("v2 state 'stage_order' must contain only strings")
            if len(stage_order) != len(set(stage_order)):
                raise ValueError("v2 state 'stage_order' contains duplicates")
            state = cls(stage_order=stage_order)
            ctx_data = data.get("context")
            if ctx_data is not None:
                if not isinstance(ctx_data, dict):
                    raise ValueError("v2 state 'context' must be a dict")
                # Reject legacy v2 states missing safety-critical resume fields.
                # These fields control ASR model selection and local-only privacy;
                # guessing defaults could silently change transcription quality
                # or leak data to remote APIs.
                _REQUIRED_RESUME_FIELDS = {"asr_model", "local_only"}
                missing = _REQUIRED_RESUME_FIELDS - ctx_data.keys()
                if missing:
                    raise ValueError(
                        "v2 state context missing safety-critical resume fields: "
                        f"{', '.join(sorted(missing))}. "
                        "旧版 pipeline state 缺少可靠恢复所需字段，请重新运行任务"
                    )
                state.context = PipelineRunContext.from_dict(ctx_data)
        else:
            raise ValueError(f"unsupported pipeline-state version: {version}")

        stages_data = data.get("stages", {})
        if not isinstance(stages_data, dict):
            raise ValueError("pipeline-state.json 'stages' must be a dict")

        for name, stage_data in stages_data.items():
            if name in state.stages:
                if not isinstance(stage_data, dict):
                    raise ValueError(f"stage '{name}' data must be a dict")
                status_val = stage_data.get("status")
                if status_val not in _VALID_STATUSES:
                    raise ValueError(
                        f"stage '{name}' has invalid status: {status_val!r}"
                    )
                s = state.stages[name]
                s.status = StageStatus(status_val)
                s.retry_count = stage_data.get("retry_count", 0)
                s.max_retries = stage_data.get("max_retries", 3)
                s.error_msg = stage_data.get("error_msg", "")
                s.result = stage_data.get("result", {})
                s.duration_sec = stage_data.get("duration_sec", 0.0)

        # Validate stages keys match stage_order
        if version == 2:
            expected = set(state.stage_order)
            actual = set(stages_data.keys())
            if actual and actual != expected:
                logger.warning(
                    "stages keys %s don't match stage_order %s",
                    actual,
                    expected,
                )

        return state

    def save(self, path: Path) -> None:
        """Atomically save state to file."""
        data = self.to_dict()
        fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
        except Exception:
            os.unlink(tmp_path)
            raise

    @classmethod
    def load(cls, path: Path) -> "PipelineState":
        """Load state from file.

        Raises:
            FileNotFoundError: if state file does not exist.
            ValueError: if state file is corrupt or has invalid schema.
        """
        try:
            with open(path) as f:
                data = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"状态文件不存在：{path}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"pipeline-state.json 无法读取或格式无效：{exc}") from exc

        if not isinstance(data, dict) or "stages" not in data:
            raise ValueError("pipeline-state.json 无法读取或格式无效：缺少 stages 字段")

        try:
            return cls.from_dict(data)
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError(f"pipeline-state.json 无法读取或格式无效：{exc}") from exc
