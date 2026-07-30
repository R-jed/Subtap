"""Observer-process helpers for reading pipeline event logs."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from enum import Enum
import io
import json
import logging
import os
from pathlib import Path
import subprocess
import time
from typing import Any

from subtap.engine.state import STAGE_CN

logger = logging.getLogger(__name__)
_UNSET = object()

LIVE_STATUSES = frozenset({"starting", "running", "stopping"})

SUBTAP_ASCII = """
█▀▀ █ █ █▀▄ ▀█▀ ▄▀█ █▀█
▄██ █▄█ █▄▀  █  █▀█ █▀▀
"""

_OBSERVED_STAGE_ORDER = [
    "prepare",
    "chunk",
    "asr",
    "clean",
    "segment",
    "align",
    "hotword",
    "learn",
    "export",
]
_OBSERVED_STAGE_CN = {
    **STAGE_CN,
    "script_match": "文稿匹配",
    "hotword": "热词替换",
    "learn": "热词学习",
    "translate": "字幕翻译",
}


@dataclass(frozen=True)
class TaskPresentation:
    """Stable task view consumed by live and historical observer screens."""

    status: str
    stage: str
    progress: int | None
    model: str
    counts: str
    current_work: str
    stage_lines: tuple[str, ...]
    recent_texts: tuple[str, ...]
    output_text: str
    state: "TaskState"
    elapsed_sec: int
    stage_durations: tuple[tuple[str, float], ...]
    current_stage_elapsed_sec: int | None = None
    allowed_actions: tuple[str, ...] = ()
    completed_stage_count: int = 0
    total_stage_count: int = 0
    subtitle_count: int | None = None
    quality_label: str = "质量模式未记录"
    failed_stage: str | None = None
    error_message: str | None = None
    retryable: bool = False


class TaskState(Enum):
    """Pipeline state independent from localized presentation copy."""

    RECORDED = "recorded"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    OBSERVATION_ERROR = "observation_error"


def iter_event_log(log_path: Path) -> list[dict[str, Any]]:
    """Read run.log.jsonl rows that were fully written."""
    if not log_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    raw_lines = log_path.read_text(encoding="utf-8").splitlines(keepends=True)
    for line_number, line in enumerate(raw_lines, start=1):
        if not line.strip():
            continue
        if line_number == len(raw_lines) and not line.endswith(("\n", "\r")):
            break
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"任务日志第 {line_number} 行损坏：{log_path}:{line_number}"
            ) from error
        if not isinstance(row, dict) or not isinstance(row.get("data", {}), dict):
            raise ValueError(
                f"任务日志第 {line_number} 行格式无效：{log_path}:{line_number}"
            )
        schema_version = row.get("schema_version", 1)
        if schema_version not in {1, 2}:
            raise ValueError(
                f"不支持的任务日志版本 {schema_version}：" f"{log_path}:{line_number}"
            )
        if schema_version == 2 and not row.get("run_id"):
            raise ValueError(
                f"任务日志第 {line_number} 行缺少任务标识：" f"{log_path}:{line_number}"
            )
        rows.append(row)
    return rows


def _new_observer_state() -> dict[str, Any]:
    """Return a clean observer state dict."""
    return {
        "stage": "等待中",
        "progress": None,
        "chunk_id": None,
        "model": "未知",
        "asr_model": None,
        "asr_drafts": 0,
        "aligned": 0,
        "completed_stages": [],
        "item_index": None,
        "total_items": None,
        "recent_texts": [],
        "started_at": None,
        "last_event_at": None,
        "stage_progress": None,
        "stage_order": [],
        "has_pipeline_plan": False,
        "run_id": None,
        "pipeline_status": None,
        "stage_durations": {},
        "stage_started_at": {},
        "stage_statuses": {},
        "schema_version": 1,
        "output_ready": None,
        "subtitle_count": None,
        "error_code": None,
        "error_message": None,
        "retryable": False,
        "pipeline_duration_sec": None,
    }


def _apply_event_row(
    state: dict[str, Any],
    row: dict[str, Any],
    *,
    recent_limit: int,
) -> None:
    """Apply one validated event row to an observer state dict."""
    event_type = row.get("event_type")
    data = row.get("data") or {}
    state["schema_version"] = max(
        state["schema_version"], int(row.get("schema_version") or 1)
    )
    if state["run_id"] is None:
        state["run_id"] = row.get("run_id") or data.get("task_id")
    if state["started_at"] is None:
        state["started_at"] = row.get("timestamp")
    if row.get("timestamp") is not None:
        state["last_event_at"] = row["timestamp"]
    row_schema = int(row.get("schema_version") or 1)
    if row_schema >= 2:
        if event_type in {"stage_start", "stage_end"} and not data.get("stage"):
            raise ValueError(f"{event_type} 事件缺少处理阶段")
        if event_type == "pipeline_plan" and not data.get("stages"):
            raise ValueError("任务计划事件缺少处理阶段")
    if event_type == "pipeline_plan" and data.get("stages"):
        state["stage_order"] = list(data["stages"])
        state["has_pipeline_plan"] = True
    if "stage" in data:
        state["stage"] = data["stage"]
    if event_type == "stage_start":
        if data.get("stage") and row.get("timestamp") is not None:
            state["stage_started_at"][data["stage"]] = row["timestamp"]
            state["stage_statuses"][data["stage"]] = "running"
        state["stage_progress"] = None
        state["item_index"] = None
        state["total_items"] = None
    if "progress" in data:
        state["stage_progress"] = data["progress"]
    if "chunk_id" in data:
        state["chunk_id"] = data["chunk_id"]
    if "model" in data:
        state["model"] = data["model"]
        if str(data["model"]).startswith("asr"):
            state["asr_model"] = data["model"]
    if "item_index" in data:
        state["item_index"] = data["item_index"]
    if "total_items" in data:
        state["total_items"] = data["total_items"]
    if event_type == "stage_end" and data.get("stage"):
        stage = data["stage"]
        if row_schema >= 2 and "status" not in data:
            raise ValueError(f"处理阶段 {stage} 缺少处理阶段状态")
        if row_schema >= 2 and "duration_sec" not in data:
            raise ValueError(f"处理阶段 {stage} 缺少阶段耗时")
        stage_status = data.get("status") or "success"
        if stage_status not in {"success", "failed", "skipped"}:
            raise ValueError(f"无效的处理阶段状态：{stage_status}")
        state["stage_progress"] = 100 if stage_status == "success" else None
        if stage_status == "success" and stage not in state["completed_stages"]:
            state["completed_stages"].append(stage)
        duration = data.get("duration_sec", data.get("duration"))
        if duration is None and row.get("timestamp") is not None:
            started_at = state["stage_started_at"].get(stage)
            if started_at is not None:
                duration = row["timestamp"] - started_at
        if duration is not None:
            state["stage_durations"][stage] = max(0.0, float(duration))
        state["stage_statuses"][stage] = stage_status
    if event_type == "pipeline_end":
        if row_schema >= 2:
            if "total_duration_sec" not in data:
                raise ValueError("任务结束事件缺少总耗时")
            if "output_ready" not in data:
                raise ValueError("任务结束事件缺少输出状态")
        terminal_status = data.get("status")
        if terminal_status not in {"success", "failed", "interrupted"}:
            raise ValueError(f"无效的任务结束状态：{terminal_status}")
        state["pipeline_status"] = (
            "completed" if terminal_status == "success" else terminal_status
        )
        state["output_ready"] = data.get("output_ready")
        state["subtitle_count"] = data.get("subtitle_count")
        state["error_code"] = data.get("error_code")
        state["error_message"] = data.get("error_message")
        state["retryable"] = data.get("retryable") is True
        state["pipeline_duration_sec"] = data.get(
            "total_duration_sec",
            data.get("duration_sec", data.get("duration")),
        )
    if event_type == "asr_draft_ready":
        state["asr_drafts"] += 1
        if data.get("text"):
            state.setdefault("recent_draft_texts", deque(maxlen=recent_limit)).append(
                data["text"]
            )
    if event_type == "alignment_ready":
        state["aligned"] += 1
        if data.get("text"):
            state.setdefault("recent_aligned_texts", deque(maxlen=recent_limit)).append(
                data["text"]
            )


def _summarize_event_rows(
    rows: list[dict[str, Any]], *, recent_limit: int = 4
) -> dict[str, Any]:
    """Reduce validated event rows into the latest pipeline state."""
    if recent_limit < 1:
        raise ValueError("recent_limit must be at least 1")
    state = _new_observer_state()
    state["recent_draft_texts"] = deque(maxlen=recent_limit)
    state["recent_aligned_texts"] = deque(maxlen=recent_limit)
    for row in rows:
        _apply_event_row(state, row, recent_limit=recent_limit)
    state["progress"] = state["stage_progress"]
    state["recent_texts"] = _recent_texts_from_state(state)
    return state


def _recent_texts_from_state(state: dict[str, Any]) -> list[str]:
    """Build the recent_texts list from internal deques."""
    aligned = state.get("recent_aligned_texts") or ()
    draft = state.get("recent_draft_texts") or ()
    return list(aligned) if aligned else list(draft)


class EventLogCursor:
    """Incremental reader for run.log.jsonl that tracks offset and inode."""

    def __init__(
        self,
        log_path: Path,
        *,
        recent_limit: int = 12,
        expected_run_id: str | None = None,
    ) -> None:
        self._path = log_path
        self._recent_limit = recent_limit
        self._expected_run_id = expected_run_id
        self._offset = 0
        self._inode: int | None = None
        self._partial = b""
        self._parsed_count = 0
        self._state = _new_observer_state()
        self._state["recent_draft_texts"] = deque(maxlen=recent_limit)
        self._state["recent_aligned_texts"] = deque(maxlen=recent_limit)

    @property
    def state(self) -> dict[str, Any]:
        return self._state

    def _finalize(self) -> None:
        self._state["progress"] = self._state["stage_progress"]
        self._state["recent_texts"] = _recent_texts_from_state(self._state)

    def read_initial(self) -> dict[str, Any]:
        """Full cold read from offset 0. Returns the finalized state."""
        self._offset = 0
        self._inode = None
        self._partial = b""
        self._parsed_count = 0
        self._state = _new_observer_state()
        self._state["recent_draft_texts"] = deque(maxlen=self._recent_limit)
        self._state["recent_aligned_texts"] = deque(maxlen=self._recent_limit)
        return self.read_updates()

    def read_updates(self) -> dict[str, Any]:
        """Read only newly appended bytes and apply them. Returns finalized state."""
        try:
            current_stat = self._path.stat()
        except FileNotFoundError:
            self._finalize()
            return self._state

        current_inode = current_stat.st_ino
        file_size = current_stat.st_size

        if self._inode is None:
            self._inode = current_inode
            self._offset = 0
            self._partial = b""

        if current_inode != self._inode:
            self._offset = 0
            self._inode = current_inode
            self._partial = b""
            self._parsed_count = 0
            self._state = _new_observer_state()
            self._state["recent_draft_texts"] = deque(maxlen=self._recent_limit)
            self._state["recent_aligned_texts"] = deque(maxlen=self._recent_limit)

        if file_size < self._offset:
            self._offset = 0
            self._partial = b""
            self._parsed_count = 0
            self._state = _new_observer_state()
            self._state["recent_draft_texts"] = deque(maxlen=self._recent_limit)
            self._state["recent_aligned_texts"] = deque(maxlen=self._recent_limit)

        if file_size == self._offset:
            self._finalize()
            return self._state

        with self._path.open("rb") as f:
            f.seek(self._offset)
            new_bytes = f.read()

        self._offset += len(new_bytes)
        raw = self._partial + new_bytes
        self._partial = b""

        lines = raw.split(b"\n")
        if raw and not raw.endswith(b"\n"):
            self._partial = lines.pop()

        for line_bytes in lines:
            if not line_bytes.strip():
                continue
            try:
                row = json.loads(line_bytes)
            except json.JSONDecodeError:
                raise ValueError(
                    f"任务日志行损坏：{self._path} (offset {self._offset})"
                )
            if not isinstance(row, dict) or not isinstance(row.get("data", {}), dict):
                raise ValueError(
                    f"任务日志行格式无效：{self._path} (offset {self._offset})"
                )
            schema_version = row.get("schema_version", 1)
            if schema_version not in {1, 2}:
                raise ValueError(f"不支持的任务日志版本 {schema_version}：{self._path}")
            if schema_version == 2 and not row.get("run_id"):
                raise ValueError(
                    f"任务日志行缺少任务标识：{self._path} (offset {self._offset})"
                )
            if (
                schema_version >= 2
                and self._expected_run_id is not None
                and row.get("run_id") != self._expected_run_id
            ):
                raise ValueError(
                    f"任务日志行任务标识不匹配：{self._path} "
                    f"(期望 {self._expected_run_id}，实际 {row.get('run_id')})"
                )
            _apply_event_row(self._state, row, recent_limit=self._recent_limit)
            self._parsed_count += 1

        self._finalize()
        return self._state


def summarize_event_log(log_path: Path) -> dict[str, Any]:
    """Build the latest observable pipeline state from run.log.jsonl."""
    return _summarize_event_rows(iter_event_log(log_path))


def build_task_presentation(
    state: dict[str, Any],
    *,
    returncode: int | None | object = _UNSET,
    output_path: Path | None = None,
    now: float | None = None,
) -> TaskPresentation:
    """Translate reducer state into one shared task presentation."""
    terminal = state.get("pipeline_status")
    terminal_key = terminal if isinstance(terminal, str) else None
    terminal_state = {
        "completed": TaskState.COMPLETED,
        "failed": TaskState.FAILED,
        "interrupted": TaskState.INTERRUPTED,
    }.get(terminal_key or "")
    if returncode is _UNSET and terminal_state is None:
        status, task_state = "任务记录", TaskState.RECORDED
    elif terminal_state is not None and returncode in {_UNSET, None}:
        assert terminal_state is not None
        task_state = terminal_state
        status = {
            TaskState.COMPLETED: "任务已完成",
            TaskState.FAILED: "任务失败",
            TaskState.INTERRUPTED: "任务已中断",
        }[task_state]
    elif returncode is None:
        status = "任务运行中"
        task_state = TaskState.RUNNING
    elif returncode == 0 and terminal_state in {None, TaskState.COMPLETED}:
        status = (
            "任务已完成"
            if output_path is None or output_path.is_file()
            else "任务异常：未找到字幕文件"
        )
        task_state = (
            TaskState.COMPLETED
            if output_path is None or output_path.is_file()
            else TaskState.FAILED
        )
    elif returncode not in {None, 0} and terminal_state in {None, TaskState.FAILED}:
        status = f"任务失败（退出码 {returncode}）"
        task_state = TaskState.FAILED
    else:
        status = "任务状态未知：进程结果与任务日志不一致"
        task_state = TaskState.OBSERVATION_ERROR

    if (
        state.get("schema_version", 1) >= 2
        and returncode is not _UNSET
        and returncode is not None
        and terminal_state is None
    ):
        status = "任务状态未知：缺少结束事件"
        task_state = TaskState.OBSERVATION_ERROR
    if task_state is TaskState.COMPLETED and (
        state.get("output_ready") is False
        or (output_path is not None and not output_path.is_file())
    ):
        status = "任务异常：未找到字幕文件"
        task_state = TaskState.FAILED

    completed = set(state["completed_stages"])
    current = state["stage"]

    def stage_line(stage: str) -> str:
        marker = (
            "×"
            if state["stage_statuses"].get(stage) == "failed"
            else "✓" if stage in completed else "▶" if stage == current else "·"
        )
        duration = state["stage_durations"].get(stage)
        timing = f"  {duration:.1f}s" if duration is not None else ""
        return f"{marker} {_OBSERVED_STAGE_CN.get(stage, '处理阶段')}{timing}"

    stage_lines = tuple(stage_line(stage) for stage in state["stage_order"])
    item_index = state["item_index"]
    total_items = state["total_items"]
    item_text = (
        f"当前项目：{item_index}/{total_items}"
        if item_index is not None and total_items is not None
        else (
            f"当前分块：{state['chunk_id']}"
            if state["chunk_id"] is not None
            else "当前任务"
        )
    )
    elapsed = 0
    if state["started_at"] is not None:
        end_time = (
            now if returncode is None and now is not None else state["last_event_at"]
        )
        if end_time is None:
            end_time = state["started_at"]
        elapsed = max(0, int(end_time - state["started_at"]))
    if (
        task_state is not TaskState.RUNNING
        and state.get("pipeline_duration_sec") is not None
    ):
        elapsed = max(0, int(float(state["pipeline_duration_sec"])))
    current_work = f"{item_text}  已用时：{elapsed // 60:02d}:{elapsed % 60:02d}"
    current_stage_elapsed: int | None = None
    stage_started_at = state["stage_started_at"].get(current)
    if (
        stage_started_at is not None
        and current not in completed
        and now is not None
        and task_state is TaskState.RUNNING
    ):
        current_stage_elapsed = max(0, int(now - stage_started_at))

    if task_state is TaskState.RUNNING:
        output_text = f"[b]输出[/b]  {output_path or '任务完成后显示'}"
    elif task_state is TaskState.COMPLETED:
        output_text = f"[green]✓ 字幕已生成[/green]\n{output_path or '输出已就绪'}"
    elif task_state is TaskState.FAILED and output_path is not None:
        reason = "未找到字幕文件" if "未找到字幕文件" in status else "未生成可交付字幕"
        output_text = f"[red]{reason}[/red]\n{output_path}"
    elif returncode is _UNSET:
        output_text = f"[b]输出[/b]  {output_path or '未记录'}"
    else:
        output_text = "[red]未生成可交付字幕[/red]"

    allowed_actions = {
        TaskState.RUNNING: ("details", "diagnostics", "detach", "stop"),
        TaskState.COMPLETED: (
            "open_output",
            "open_directory",
            "new_task",
            "details",
        ),
        TaskState.FAILED: ("diagnostics", "new_task", "details"),
        TaskState.INTERRUPTED: ("diagnostics", "new_task", "details"),
        TaskState.OBSERVATION_ERROR: ("diagnostics", "details"),
        TaskState.RECORDED: ("details",),
    }[task_state]
    model_name = str(state.get("asr_model") or state.get("model") or "")
    quality_label = (
        "高质量 · 1.7B"
        if "1.7b" in model_name.casefold()
        else "快速 · 0.6B" if "0.6b" in model_name.casefold() else "质量模式未记录"
    )
    failed_stage = next(
        (
            _OBSERVED_STAGE_CN.get(stage, "处理阶段")
            for stage, stage_status in state["stage_statuses"].items()
            if stage_status == "failed"
        ),
        None,
    )

    return TaskPresentation(
        status=status,
        stage=str(state["stage"]),
        progress=state["progress"],
        model=str(state["model"]),
        counts=f"ASR 草稿：{state['asr_drafts']}  已对齐：{state['aligned']}",
        current_work=current_work,
        stage_lines=stage_lines,
        recent_texts=tuple(state["recent_texts"]),
        output_text=output_text,
        state=task_state,
        elapsed_sec=elapsed,
        stage_durations=tuple(state["stage_durations"].items()),
        current_stage_elapsed_sec=current_stage_elapsed,
        allowed_actions=allowed_actions,
        completed_stage_count=len(completed),
        total_stage_count=len(state["stage_order"]),
        subtitle_count=state.get("subtitle_count"),
        quality_label=quality_label,
        failed_stage=failed_stage,
        error_message=state.get("error_message") or state.get("error_code"),
        retryable=state.get("retryable") is True,
    )


# ── Positive process-identity TTL cache ──────────────────────────────
# Stores (pid, task_id) -> last_successful_verification (time.monotonic).
# Only successful run-id verification results are cached.
# PID liveness is ALWAYS checked first — before cache lookup.
_IDENTITY_CACHE_TTL = 5.0
_IDENTITY_CACHE_MAX_ENTRIES = 64
_IDENTITY_CACHE: dict[tuple[int, str], float] = {}


def _evict_identity_cache(pid: int | None, task_id: str | None) -> None:
    """Remove positive cache entry for *pid* × *task_id*."""
    if not isinstance(pid, int):
        return
    if task_id is None:
        # Evict all entries for this PID.
        stale = [k for k in _IDENTITY_CACHE if k[0] == pid]
        for k in stale:
            _IDENTITY_CACHE.pop(k, None)
    else:
        _IDENTITY_CACHE.pop((pid, task_id), None)


def _prune_identity_cache(now: float) -> None:
    """Remove all expired positive cache entries."""
    stale = [
        k for k, ts in _IDENTITY_CACHE.items() if (now - ts) >= _IDENTITY_CACHE_TTL
    ]
    for k in stale:
        _IDENTITY_CACHE.pop(k, None)


def persisted_process_matches_task(pid: int | None, task_id: str | None) -> bool:
    """Return True only when *pid* is alive AND carries SUBTAP_RUN_ID=<task_id>.

    Positive verification results are cached for ``_IDENTITY_CACHE_TTL``
    seconds.  PID liveness is still checked on every invocation — the cache
    only avoids the expensive ``ps eww`` subprocess when both the PID is
    alive and a recent verification entry exists.
    """
    # ── 1. PID liveness (always checked) ──
    if not isinstance(pid, int) or not _pid_is_alive(pid):
        _evict_identity_cache(pid, task_id)
        return False

    # ── 2. No task_id — legacy PID-only path ──
    if task_id is None:
        return True

    # ── 3. Positive cache hit inside TTL ──
    now = time.monotonic()
    key = (pid, task_id)
    cached_ts = _IDENTITY_CACHE.get(key)
    if cached_ts is not None and (now - cached_ts) < _IDENTITY_CACHE_TTL:
        return True

    # ── 4. Cache miss — run identity verifier ──
    from subtap.cli.pipeline_cli import _observer_process_matches_run_id

    if _observer_process_matches_run_id(pid, task_id):
        # Opportunistic eviction before insert.
        if len(_IDENTITY_CACHE) >= _IDENTITY_CACHE_MAX_ENTRIES:
            _prune_identity_cache(now)
            # Prune only removes expired entries.  If all within TTL,
            # evict the oldest surviving entry.
            if len(_IDENTITY_CACHE) >= _IDENTITY_CACHE_MAX_ENTRIES:
                oldest_key = min(_IDENTITY_CACHE, key=lambda k: _IDENTITY_CACHE[k])
                _IDENTITY_CACHE.pop(oldest_key, None)
        _IDENTITY_CACHE[key] = now
        return True

    # ── 5. Identity mismatch — never cache False ──
    _IDENTITY_CACHE.pop(key, None)
    return False


def build_task_presentation_from_log(
    log_path: Path,
    *,
    output_path: Path | None = None,
    process: Any | None = None,
    pid: int | None = None,
    now: float | None = None,
    run_id: str | None = None,
) -> TaskPresentation:
    """Build a live or historical task view without confusing the two.

    When *run_id* is provided without a live *process* or *pid*, the log is
    read through an ``EventLogCursor`` that validates every v2 row against
    the expected run-id.  If the log passes identity validation but contains
    no terminal event the result is ``OBSERVATION_ERROR`` (the caller can
    persist that to avoid repeat scans).
    """
    if process is None and pid is None and run_id is not None:
        try:
            cursor = EventLogCursor(
                log_path,
                recent_limit=12,
                expected_run_id=run_id,
            )
            cursor.read_initial()
            state = cursor.state
        except (OSError, ValueError) as error:
            return build_observation_error_presentation(error)

        pipeline_status = state.get("pipeline_status")
        if pipeline_status:
            returncode: int | object = 0
            if pipeline_status == "completed":
                pass
            elif pipeline_status == "interrupted":
                returncode = _UNSET
            else:
                returncode = 1
            return build_task_presentation(
                state,
                returncode=returncode,
                output_path=output_path,
                now=now,
            )

        recorded = build_task_presentation(
            state,
            returncode=_UNSET,
            output_path=output_path,
            now=now,
        )
        return build_observation_error_presentation(
            RuntimeError("任务日志不完整：未找到任务结束记录"),
            recorded,
        )

    state = summarize_event_log(log_path)
    if process is None:
        if pid is not None:
            if persisted_process_matches_task(pid, run_id):
                return build_task_presentation(
                    state,
                    returncode=None,
                    output_path=output_path,
                    now=now,
                )
            recorded = build_task_presentation(
                state,
                returncode=_UNSET,
                output_path=output_path,
                now=now,
            )
            return build_observation_error_presentation(
                RuntimeError("无法确认任务进程仍在运行"),
                recorded,
            )
        return build_task_presentation(
            state,
            returncode=_UNSET,
            output_path=output_path,
            now=now,
        )

    returncode = process.poll()
    if returncode is not None:
        return build_task_presentation(
            state,
            returncode=returncode,
            output_path=output_path,
            now=now,
        )

    pid = getattr(process, "pid", None)
    if not persisted_process_matches_task(pid, run_id):
        recorded = build_task_presentation(
            state,
            returncode=_UNSET,
            output_path=output_path,
            now=now,
        )
        return build_observation_error_presentation(
            RuntimeError("无法确认任务进程仍在运行"),
            recorded,
        )

    return build_task_presentation(
        state,
        returncode=None,
        output_path=output_path,
        now=now,
    )


def _pid_is_alive(pid: object) -> bool:
    """Return true only when the operating system confirms a live PID."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def build_observation_error_presentation(
    error: Exception,
    previous: TaskPresentation | None = None,
) -> TaskPresentation:
    """Preserve the last trustworthy view when new observer data is invalid."""
    if previous is None:
        previous = build_task_presentation(_summarize_event_rows([]))
    return replace(
        previous,
        status=f"任务状态未知：{error}",
        state=TaskState.OBSERVATION_ERROR,
        allowed_actions=("diagnostics", "back"),
    )


def build_task_status_text(presentation: TaskPresentation) -> str:
    progress_text = (
        f"{presentation.progress}%" if presentation.progress is not None else "计算中"
    )
    return (
        f"[b]{presentation.status}[/b]\n"
        f"当前阶段：{presentation.stage}\n"
        f"进度：{progress_text}\n"
        f"当前模型：{presentation.model}\n"
        f"{presentation.counts}\n"
        f"{presentation.current_work}\n"
        "隐私：观察者只读取本地日志，不接触音频和模型推理\n"
        f"{presentation.output_text}"
    )


def build_command_deck_text(state: dict[str, Any]) -> str:
    """Format pipeline state as human-readable text for CLI output."""
    return build_task_status_text(build_task_presentation(state))


def _make_observer_dashboard(
    log_path: Path,
    process,
    refresh_interval: float = 1.0,
    output_path: Path | None = None,
):
    """Create ObserverDashboard instance (lazy import of textual)."""
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Grid, Vertical, VerticalScroll
    from textual.screen import ModalScreen
    from textual.widgets import Footer, ProgressBar, RichLog, Static
    from rich.text import Text
    from subtap.ui.theme import CALM_WORKBENCH_BREAKPOINTS, CALM_WORKBENCH_CSS

    class CancelTaskScreen(ModalScreen[bool]):
        """Require an explicit answer before stopping the pipeline."""

        CSS = """
        CancelTaskScreen {
            align: center middle;
            background: $background 70%;
        }
        #cancel-dialog {
            width: 58;
            height: auto;
            padding: 2 3;
            border: round $error;
            background: $surface;
        }
        """
        BINDINGS = [
            ("y", "confirm", "确认停止"),
            ("n", "keep_running", "继续运行"),
            ("escape", "keep_running", "返回"),
        ]

        def compose(self) -> ComposeResult:
            with Vertical(id="cancel-dialog"):
                yield Static(
                    "[b]停止当前任务？[/b]\n\n"
                    "这会终止字幕处理；已生成的工作文件会保留。\n\n"
                    "按 Y 确认，按 N 或 Esc 返回。"
                )

        def action_confirm(self) -> None:
            self.dismiss(True)

        def action_keep_running(self) -> None:
            self.dismiss(False)

    class ObserverDashboard(App):
        """Textual 观察者：只读 run.log.jsonl，不执行 pipeline。"""

        HORIZONTAL_BREAKPOINTS = CALM_WORKBENCH_BREAKPOINTS
        CSS = CALM_WORKBENCH_CSS + """
        Screen {
            layout: vertical;
            align: center top;
        }
        #task-panel {
            width: 100%;
            max-width: 104;
            height: 1fr;
            padding: 1 2 0 2;
        }
        #status {
            height: auto;
            padding-bottom: 1;
        }
        #progress { margin-bottom: 1; }
        #task-layout {
            grid-size: 2 1;
            grid-columns: 2fr 3fr;
            grid-rows: auto;
            grid-gutter: 1 2;
            height: auto;
        }
        #pipeline-pane, #activity-pane {
            height: auto;
            padding: 1 2;
            background: $surface;
        }
        .-compact #task-layout {
            grid-size: 1 2;
            grid-columns: 1fr;
            grid-rows: auto auto;
        }
        #stage-map, #recent, #output {
            margin-top: 1;
        }
        #details {
            width: 100%;
            max-width: 104;
            margin-bottom: 1;
            border: round $secondary;
            height: 1fr;
            display: none;
        }
        """
        BINDINGS = [
            ("l", "toggle_details", "详情"),
            ("f", "open_output_directory", "输出目录"),
            ("d", "open_diagnostics", "诊断日志"),
            ("escape", "show_overview", "返回概览"),
            Binding("q", "quit_observer", "退出观察", priority=True),
            ("x", "cancel_task", "停止任务"),
        ]

        def __init__(self) -> None:
            super().__init__()
            self._task_running = True

        def compose(self) -> ComposeResult:
            with VerticalScroll(id="task-panel"):
                yield Static(self.build_status_text(), id="status")
                yield ProgressBar(total=100, show_eta=False, id="progress")
                yield Static("", id="current-work")
                with Grid(id="task-layout"):
                    with Vertical(id="pipeline-pane"):
                        yield Static("", id="stage-map")
                    with Vertical(id="activity-pane"):
                        yield Static("", id="recent")
                        yield Static("", id="output")
                        yield Static("", id="action-status")
            yield RichLog(max_lines=200, auto_scroll=True, id="details")
            yield Footer()

        async def on_mount(self) -> None:
            self.set_interval(refresh_interval, self.refresh_from_log)
            self.refresh_from_log()

        def build_status_text(
            self,
            state: dict[str, Any] | None = None,
            returncode: Any = _UNSET,
        ) -> str:
            if state is None:
                state = summarize_event_log(log_path)
            if returncode is _UNSET:
                returncode = process.poll()
            presentation = build_task_presentation(
                state,
                returncode=returncode,
                output_path=output_path,
                now=time.time(),
            )
            return build_task_status_text(presentation)

        def refresh_from_log(self) -> None:
            rows = iter_event_log(log_path)
            state = _summarize_event_rows(rows)
            returncode = process.poll()
            presentation = build_task_presentation(
                state,
                returncode=returncode,
                output_path=output_path,
                now=time.time(),
            )
            self._task_running = returncode is None
            self.refresh_bindings()
            self.query_one("#status", Static).update(
                build_task_status_text(presentation)
            )

            bar = self.query_one("#progress", ProgressBar)
            if presentation.progress is None:
                bar.update(total=None)
            else:
                bar.update(total=100, progress=presentation.progress)
            self.query_one("#stage-map", Static).update(
                "[b]处理流程[/b]\n" + "\n".join(presentation.stage_lines)
            )
            self.query_one("#current-work", Static).update(presentation.current_work)

            recent_text = "\n".join(f"  {text}" for text in presentation.recent_texts)
            self.query_one("#recent", Static).update(
                f"[b]最近字幕[/b]\n{recent_text or '  暂无'}"
            )
            self.query_one("#output", Static).update(presentation.output_text)

            details = self.query_one("#details", RichLog)
            details.clear()
            for row in rows[-50:]:
                data = row.get("data") or {}
                message = data.get("message_zh") or row.get("event_type", "未知事件")
                details.write(f"{data.get('stage', '-'):>8}  {message}")

        def action_toggle_details(self) -> None:
            details = self.query_one("#details", RichLog)
            details.display = not details.display
            self.query_one("#task-panel").display = not details.display

        def _open_path(self, target: Path, label: str) -> None:
            status = self.query_one("#action-status", Static)
            try:
                result = subprocess.run(
                    ["open", str(target)],
                    capture_output=True,
                    text=True,
                )
            except OSError as error:
                logger.exception("打开%s失败：%s", label, target)
                status.update(f"打开{label}失败：{error}")
                return
            if result.returncode:
                detail = result.stderr.strip() or f"退出码 {result.returncode}"
                logger.error("打开%s失败：%s", label, detail)
                status.update(Text(f"打开{label}失败：{detail}"))
            else:
                status.update(f"已打开{label}。")

        def _open_completed_result(self, target: Path, label: str) -> None:
            status = self.query_one("#action-status", Static)
            if process.poll() is None:
                status.update("任务完成后才能打开结果。")
                return
            if (
                process.returncode != 0
                or output_path is None
                or not output_path.is_file()
            ):
                status.update("没有可打开的字幕结果。")
                return
            self._open_path(target, label)

        def action_open_output_directory(self) -> None:
            if output_path is None:
                self.query_one("#action-status", Static).update(
                    "没有可打开的字幕结果。"
                )
                return
            self._open_completed_result(output_path.parent, "输出目录")

        def action_open_diagnostics(self) -> None:
            status = self.query_one("#action-status", Static)
            diagnostic_path = log_path.with_name("run_latest.log")
            if process.poll() is None:
                status.update("任务结束后才能打开诊断日志。")
            elif not diagnostic_path.is_file():
                status.update(f"未找到诊断日志：{diagnostic_path}")
            else:
                self._open_path(diagnostic_path, "诊断日志")

        def action_show_overview(self) -> None:
            self.query_one("#details", RichLog).display = False
            self.query_one("#task-panel").display = True

        def action_quit_observer(self) -> None:
            self.exit("quit")

        def check_action(self, action: str, parameters: tuple[object, ...]) -> bool:
            if action == "cancel_task":
                return self._task_running
            return True

        def action_cancel_task(self) -> None:
            if process.poll() is None:
                self.push_screen(CancelTaskScreen(), self._finish_cancel)

        def _finish_cancel(self, confirmed: bool | None) -> None:
            if confirmed and process.poll() is None:
                self.exit("interrupt")
            elif confirmed:
                self.refresh_from_log()

    return ObserverDashboard()
