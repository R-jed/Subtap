"""Progress display system using rich."""

from __future__ import annotations

from rich.console import Console
from rich.progress import (
    Progress,
)
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from subtap.ui.state import PipelineState, STAGE_ORDER, STAGE_CN

console = Console()


def _build_stage_table(state: PipelineState, completed_stages: list[str]) -> Table:
    """Build the stage overview table."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("status", width=3)
    table.add_column("stage", width=12)
    table.add_column("name", width=12)

    for s in STAGE_ORDER:
        if s in completed_stages:
            icon = "[green]✓[/green]"
        elif s == state.stage:
            icon = "[yellow]▸[/yellow]"
        else:
            icon = "[dim]○[/dim]"
        table.add_row(icon, STAGE_CN.get(s, s), f"[dim]{s}[/dim]")

    return table


class PipelineProgress:
    """Rich-based progress display for pipeline execution."""

    def __init__(self):
        self.console = console
        self.completed_stages: list[str] = []
        self._progress: Progress | None = None
        self._task_id = None

    def on_state_change(self, state: PipelineState) -> None:
        """Callback for pipeline state changes."""
        if state.status == "completed" and state.stage not in self.completed_stages:
            self.completed_stages.append(state.stage)

    def print_header(self) -> None:
        """Print the TUI header."""
        self.console.print()
        self.console.print(
            Panel(
                Text("Subtap 字幕生成引擎", style="bold cyan", justify="center"),
                border_style="cyan",
                padding=(0, 2),
            )
        )

    def print_stage_start(self, state: PipelineState) -> None:
        """Print stage start with Chinese name."""
        idx = STAGE_ORDER.index(state.stage) + 1 if state.stage in STAGE_ORDER else 0
        total = len(STAGE_ORDER)
        self.console.print(
            f"\n[bold cyan]▸ [{idx}/{total}] {state.stage_cn}[/bold cyan]"
        )
        if state.current_task:
            self.console.print(f"  [dim]{state.current_task}[/dim]")

    def print_stage_result(self, state: PipelineState, result: dict) -> None:
        """Print stage completion."""
        # Extract key info from result
        parts = []
        if "media_info" in result:
            mi = result["media_info"]
            parts.append(f"{mi['duration']:.1f}s, {mi['sample_rate']}Hz")
        elif "chunk_count" in result:
            parts.append(f"{result['chunk_count']} 段")
        elif "segment_count" in result:
            parts.append(f"{result['segment_count']} 条")
        elif "sentence_count" in result:
            parts.append(f"{result['sentence_count']} 句")
        elif "aligned_count" in result:
            parts.append(f"{result['aligned_count']} 条")
        elif "output_path" in result:
            parts.append(result["output_path"])

        detail = "，".join(parts) if parts else ""
        self.console.print(f"  [green]✓[/green] {detail}")

    def print_skip(self, stage_cn: str, reason: str = "") -> None:
        """Print stage skip."""
        msg = f"  [yellow]○ 跳过 {stage_cn}[/yellow]"
        if reason:
            msg += f" [dim]({reason})[/dim]"
        self.console.print(msg)

    def print_summary(self, timings: dict[str, float], total_time: float) -> None:
        """Print pipeline completion summary."""
        self.console.print()
        self.console.print(
            Panel(
                Text("全流程完成", style="bold green", justify="center"),
                border_style="green",
                padding=(0, 2),
            )
        )

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("stage", width=12, style="cyan")
        table.add_column("time", width=10, justify="right")

        for stage in STAGE_ORDER:
            if stage in timings:
                table.add_row(STAGE_CN.get(stage, stage), f"{timings[stage]:.1f}s")

        table.add_section()
        table.add_row("[bold]总耗时[/bold]", f"[bold]{total_time:.1f}s[/bold]")

        self.console.print(table)

    def print_error(self, error: Exception, state: PipelineState) -> None:
        """Print error with Chinese message and suggestion."""
        self.console.print()
        self.console.print(
            Panel(
                f"[bold red]✗ 处理失败[/bold red]\n\n"
                f"[red]错误：{error}[/red]\n"
                f"[yellow]阶段：{state.stage_cn or '未知'}[/yellow]",
                border_style="red",
                padding=(0, 2),
            )
        )

    def print_export_hint(self, output_dir: str, fmt: str) -> None:
        """Print export file location."""
        self.console.print(f"\n  [dim]输出目录：{output_dir}[/dim]")
        self.console.print(f"  [dim]格式：{fmt.upper()}[/dim]")

    def print_model_status(self, model_name: str, status: str) -> None:
        """Print model loading status."""
        if status == "loading":
            self.console.print(f"  [dim]加载模型：{model_name}...[/dim]")
        elif status == "ready":
            self.console.print(f"  [green]✓ 模型就绪：{model_name}[/green]")
        elif status == "error":
            self.console.print(f"  [red]✗ 模型加载失败：{model_name}[/red]")
