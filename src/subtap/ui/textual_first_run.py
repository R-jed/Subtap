"""Textual first-run screen for a complete offline setup."""

from __future__ import annotations

import logging
from threading import Event
from pathlib import Path
from typing import Any

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, ProgressBar, Select, Static
from pydantic import ValidationError
from rich.text import Text

from subtap.core.models import DownloadCancelled, required_model_names
from subtap.core.safe_delete import ensure_directory_structure
from subtap.core.user_resources import ensure_default_glossary
from subtap.core.state_store import StateStore
from subtap.schemas.config import SubtapConfig
from subtap.ui.config_manager import ConfigManager
from subtap.ui.views.first_run import FirstRunView

_GIB = 1024**3
_MIN_FREE_AFTER_DOWNLOAD = 512 * 1024**2
logger = logging.getLogger(__name__)


class FirstRunScreen(Screen[None]):
    """Install and verify the complete model set before entering Subtap."""

    CSS = """
    FirstRunScreen {
        align: center middle;
        background: #000000;
        color: #f2f2f2;
    }
    #panel {
        width: 76;
        height: auto;
        padding: 2 3;
        border: round #21c7d9;
    }
    #summary, #status {
        margin: 1 0;
    }
    #progress {
        margin: 1 0;
    }
    #selectors {
        height: 3;
    }
    #selectors Select {
        width: 1fr;
    }
    Select, Button {
        margin: 1 1 0 0;
    }
    """

    BINDINGS = [("escape", "cancel_download", "取消/退出")]

    def __init__(self) -> None:
        super().__init__()
        self.view = FirstRunView()
        self.config: SubtapConfig | None = None
        self.manager: ConfigManager | None = None
        self._plan_context: (
            tuple[dict[str, Any], ConfigManager, SubtapConfig] | None
        ) = None
        self.plan: dict[str, Any] = {}
        self.source = "hf"
        self._cancel_requested = Event()
        self._downloaded: dict[tuple[str, str], int] = {}
        self._model_selection_ready = False

    def compose(self) -> ComposeResult:
        with Vertical(id="panel"):
            yield Static("[b]首次启动[/b]\nSubtap 将检查本机并安装离线运行所需模型。")
            yield Static("正在检查设备…", id="summary")
            yield Static("", id="status")
            with Horizontal(id="selectors"):
                yield Select(
                    [
                        ("0.6B · 速度优先 · 8bit", "asr_0.6b"),
                        ("1.7B · 质量优先 · 8bit", "asr_1.7b"),
                    ],
                    value="asr_0.6b",
                    allow_blank=False,
                    id="asr-model",
                )
                yield Select(
                    [
                        ("Hugging Face", "hf"),
                        ("Hugging Face 国内镜像", "hf-mirror"),
                        ("ModelScope", "modelscope"),
                    ],
                    value="hf",
                    allow_blank=False,
                    id="source",
                )
            yield ProgressBar(total=100, id="progress")
            yield Button("下载并自检", id="download", variant="primary", disabled=True)
            yield Button("取消", id="cancel", disabled=True)
            yield Footer()

    def on_mount(self) -> None:
        device = self.view.check_device()
        runtime_ok = (
            device["is_apple_silicon"] and device["has_ffmpeg"] and device["has_mlx"]
        )
        if not runtime_ok:
            self.query_one("#status", Static).update(
                "本机环境未满足要求：需要 Apple Silicon、FFmpeg 和 MLX。"
            )
            return

        try:
            manager = ConfigManager(self._config_path())
            config = manager.to_subtap_config()
        except (RuntimeError, ValidationError) as exc:
            self.query_one("#status", Static).update(Text(f"配置文件读取失败：{exc}"))
            return

        configured_model = manager.get("asr.model", "asr_0.6b")
        config.asr.model = configured_model
        if configured_model in ("asr_0.6b", "asr_1.7b"):
            self.query_one("#asr-model", Select).value = configured_model

        self.query_one("#status", Static).update("正在校验已有模型并计算下载量…")
        self._plan_context = (device, manager, config)
        self.prepare_download_plan(device, manager, config)
        self.call_after_refresh(self._enable_model_selection)

    def _enable_model_selection(self) -> None:
        self._model_selection_ready = True

    @work(thread=True, exclusive=True, exit_on_error=False)
    def prepare_download_plan(
        self, device: dict[str, Any], manager: ConfigManager, config: SubtapConfig
    ) -> None:
        """Hash existing complete files without blocking Textual rendering."""
        free_bytes = int(device["free_gb"] * _GIB)
        try:
            selected_plan = self.view.get_download_plan(
                required_model_names(config),
                config=config,
                cancelled=self._cancel_requested.is_set,
            )
        except DownloadCancelled:
            return
        except ValueError as exc:
            self.app.call_from_thread(self._show_config_error, exc)
            return
        except Exception as exc:
            logger.exception("首次启动模型扫描失败")
            self.app.call_from_thread(self._show_plan_error, exc)
            return

        need = self._required_disk(selected_plan["download_bytes"])
        if need > free_bytes:
            self.app.call_from_thread(
                self._show_insufficient_disk, selected_plan, need, device["free_gb"]
            )
            return

        self.app.call_from_thread(
            self._apply_download_plan,
            manager,
            config,
            selected_plan,
            free_bytes,
        )

    def _show_config_error(self, exc: Exception) -> None:
        self.query_one("#status", Static).update(Text(f"配置文件读取失败：{exc}"))

    def _show_plan_error(self, exc: Exception) -> None:
        self.query_one("#status", Static).update(
            Text(f"模型扫描失败：{exc}。请检查文件权限后重试。")
        )
        button = self.query_one("#download", Button)
        button.label = "重新扫描"
        button.disabled = False

    def _show_insufficient_disk(
        self, plan: dict[str, Any], need: int, free_gb: float
    ) -> None:
        names = " + ".join(plan["model_names"])
        self.query_one("#summary", Static).update(
            f"必需模型：{names}，共 {plan['size_display']}"
        )
        self.query_one("#status", Static).update(
            f"空间不足：至少需要 {need / _GIB:.1f} GB，当前可用 {free_gb:.1f} GB。"
        )

    def _apply_download_plan(
        self,
        manager: ConfigManager,
        config: SubtapConfig,
        selected_plan: dict[str, Any],
        free_bytes: int,
    ) -> None:
        self.config = config
        self.manager = manager
        self.plan = selected_plan
        self._downloaded = dict(selected_plan["existing_bytes_by_file"])
        completed = selected_plan["size_bytes"] - selected_plan["download_bytes"]
        self._update_progress(completed, max(selected_plan["size_bytes"], 1))
        remaining = (free_bytes - selected_plan["download_bytes"]) / _GIB
        names = " + ".join(selected_plan["model_names"])
        self.query_one("#summary", Static).update(
            f"已选 ASR：{config.asr.model}（8bit）\n"
            f"对齐模型：自动安装并始终使用（8bit）\n"
            f"模型组合：{names}\n总量：{selected_plan['size_display']}  "
            f"还需下载：{selected_plan['download_bytes'] / _GIB:.1f} GB  "
            f"位置：{selected_plan['target_dir']}\n下载后预计剩余：{remaining:.1f} GB"
        )
        self.query_one("#status", Static).update("确认后开始下载；可取消并在下次继续。")
        button = self.query_one("#download", Button)
        button.label = "下载并自检"
        button.disabled = False

    @on(Select.Changed, "#asr-model")
    def select_asr_model(self, event: Select.Changed) -> None:
        if (
            not self._model_selection_ready
            or not isinstance(event.value, str)
            or self._plan_context is None
        ):
            return
        device, manager, current_config = self._plan_context
        if event.value == current_config.asr.model:
            return
        config = manager.to_subtap_config()
        config.asr.model = event.value
        self.config = None
        self._plan_context = (device, manager, config)
        self.query_one("#download", Button).disabled = True
        self.query_one("#status", Static).update("正在按所选模型重新计算下载量…")
        self.prepare_download_plan(device, manager, config)

    @staticmethod
    def _config_path() -> Path:
        return Path.home() / ".subtap" / "config.yaml"

    @staticmethod
    def _required_disk(model_bytes: int) -> int:
        return model_bytes + max(model_bytes // 10, _MIN_FREE_AFTER_DOWNLOAD)

    @on(Button.Pressed, "#download")
    def start_download(self) -> None:
        if self.config is None:
            if self._plan_context is not None:
                self._cancel_requested.clear()
                self.query_one("#download", Button).disabled = True
                self.query_one("#status", Static).update(
                    "正在校验已有模型并计算下载量…"
                )
                self.prepare_download_plan(*self._plan_context)
            return
        ensure_directory_structure(self._config_path().parent)
        ensure_default_glossary(self._config_path().parent)
        self._cancel_requested.clear()
        self._downloaded = dict(self.plan.get("existing_bytes_by_file", {}))
        source_value = self.query_one("#source", Select).value
        self.source = source_value if isinstance(source_value, str) else "hf"
        self.query_one("#download", Button).disabled = True
        self.query_one("#cancel", Button).disabled = False
        self.query_one("#status", Static).update("正在下载并校验模型…")
        self.download_models()

    @on(Button.Pressed, "#cancel")
    def cancel_button(self) -> None:
        self.action_cancel_download()

    def action_cancel_download(self) -> None:
        if not self.query_one("#cancel", Button).disabled:
            self._cancel_requested.set()
            self.query_one("#status", Static).update("正在安全停止，已下载内容会保留…")
        else:
            self._cancel_requested.set()
            self.app.exit()

    @work(thread=True, exclusive=True, exit_on_error=False)
    def download_models(self) -> None:
        assert self.config is not None
        try:
            self.view.download_required_models(
                self.config,
                source=self.source,
                progress=self._report_progress,
                cancelled=self._cancel_requested.is_set,
                verified_files=set(self.plan.get("verified_files", set())),
            )
            if self._cancel_requested.is_set():
                raise DownloadCancelled("模型下载已取消，可稍后继续")
            self.view.run_required_offline_self_check(
                self.config, cancelled=self._cancel_requested.is_set
            )
            if self._cancel_requested.is_set():
                raise DownloadCancelled("模型校验已取消，可稍后继续")
            assert self.manager is not None
            self.manager.sync_from_config(self.config)
        except DownloadCancelled:
            self.app.call_from_thread(self._download_cancelled)
        except Exception as exc:
            self.app.call_from_thread(self._download_failed, exc)
        else:
            self.app.call_from_thread(self._download_complete)

    def _report_progress(
        self, model_name: str, filename: str, downloaded: int, total: int
    ) -> None:
        self._downloaded[(model_name, filename)] = downloaded
        completed = sum(self._downloaded.values())
        total_bytes = max(int(self.plan.get("size_bytes", 0)), total, 1)
        self.app.call_from_thread(self._update_progress, completed, total_bytes)

    def _update_progress(self, completed: int, total: int) -> None:
        self.query_one("#progress", ProgressBar).update(total=total, progress=completed)

    def _download_cancelled(self) -> None:
        self.query_one("#status", Static).update(
            "下载已取消；再次开始会从已有内容继续。"
        )
        self._reset_buttons()

    def _download_failed(self, exc: Exception) -> None:
        self.plan["verified_files"] = set()
        self.query_one("#status", Static).update(
            Text(f"下载失败：{exc}。可切换来源后重试。")
        )
        self._reset_buttons()

    def _reset_buttons(self) -> None:
        self.query_one("#download", Button).disabled = False
        self.query_one("#download", Button).label = "继续/重试"
        self.query_one("#cancel", Button).disabled = True

    def _download_complete(self) -> None:
        if self._cancel_requested.is_set():
            self._download_cancelled()
            return
        self.query_one("#progress", ProgressBar).update(progress=100, total=100)
        StateStore(self.view.mark_complete()).load()
        self.dismiss()
