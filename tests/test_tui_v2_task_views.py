import pytest
from textual.app import App
from textual.widgets import ProgressBar, RichLog, Static

from subtap.ui.observer import TaskPresentation, TaskState
from subtap.ui.v2.task_views import TaskScreen


def presentation(**overrides: object) -> TaskPresentation:
    values: dict[str, object] = {
        "status": "任务运行中",
        "stage": "asr",
        "progress": 42,
        "model": "small",
        "counts": "ASR 草稿：2  已对齐：1",
        "current_work": "当前分块：3  已用时：00:12",
        "stage_lines": ("✓ 准备", "▶ 语音识别", "· 导出"),
        "recent_texts": ("第一句字幕", "第二句字幕"),
        "output_text": "[red]未生成可交付字幕[/red]",
        "state": TaskState.RUNNING,
        "elapsed_sec": 12,
        "stage_durations": (("prepare", 1.2),),
        "completed_stage_count": 1,
        "total_stage_count": 3,
    }
    values.update(overrides)
    return TaskPresentation(**values)


class TaskApp(App[None]):
    def __init__(self, task: TaskPresentation) -> None:
        super().__init__()
        self.task_presentation = task

    def on_mount(self) -> None:
        self.push_screen(TaskScreen(self.task_presentation))


async def test_running_task_shows_progress_and_live_subtitles() -> None:
    async with TaskApp(presentation()).run_test(size=(90, 56)) as pilot:
        await pilot.pause()

        assert pilot.app.screen.query_one(ProgressBar).progress == 42
        visible = "\n".join(
            str(widget.render()) for widget in pilot.app.screen.query(Static)
        )
        assert "任务运行中" in visible
        assert "处理流程" in visible
        assert "已完成 1/3 阶段" in visible
        assert "详情" in visible
        subtitles = "\n".join(
            str(line) for line in pilot.app.screen.query_one(RichLog).lines
        )
        assert "第一句字幕" in subtitles


async def test_compact_running_task_folds_pipeline_rail() -> None:
    async with TaskApp(presentation()).run_test(size=(70, 30)) as pilot:
        await pilot.pause()

        screen = pilot.app.screen
        assert "-compact" in screen.classes
        assert screen.query_one("#task-pipeline").display is False
        assert screen.query_one("#task-view").max_scroll_x == 0


async def test_running_task_does_not_invent_unknown_progress_or_pipeline() -> None:
    task = presentation(progress=None, stage_lines=(), recent_texts=())
    async with TaskApp(task).run_test(size=(90, 56)) as pilot:
        await pilot.pause()

        assert not list(pilot.app.screen.query(ProgressBar))
        visible = "\n".join(
            str(widget.render()) for widget in pilot.app.screen.query(Static)
        )
        assert "等待任务公布处理流程" in visible
        subtitles = "\n".join(
            str(line) for line in pilot.app.screen.query_one(RichLog).lines
        )
        assert "正在识别" in subtitles


async def test_completed_task_prioritizes_output_and_actions() -> None:
    task = presentation(
        status="任务已完成",
        progress=100,
        output_text="[green]✓ 字幕已生成[/green]\n/tmp/result.srt",
        state=TaskState.COMPLETED,
        elapsed_sec=50,
        subtitle_count=39,
        quality_label="高质量 · 1.7B",
    )
    async with TaskApp(task).run_test(size=(90, 56)) as pilot:
        await pilot.pause()

        visible = "\n".join(
            str(widget.render()) for widget in pilot.app.screen.query(Static)
        )
        assert not list(pilot.app.screen.query(ProgressBar))
        assert "字幕已生成" in visible
        assert "/tmp/result.srt" in visible
        assert "字幕 39 条" in visible
        assert "高质量 · 1.7B" in visible
        assert "打开字幕" in visible
        assert "打开所在目录" in visible


async def test_completed_task_does_not_invent_unknown_subtitle_count() -> None:
    task = presentation(
        status="任务已完成",
        output_text="[green]✓ 字幕已生成[/green]\n/tmp/result.srt",
        state=TaskState.COMPLETED,
        subtitle_count=None,
    )
    async with TaskApp(task).run_test(size=(90, 56)) as pilot:
        await pilot.pause()
        visible = "\n".join(
            str(widget.render()) for widget in pilot.app.screen.query(Static)
        )

        assert "字幕数量未记录" in visible
        assert "字幕 0 条" not in visible


async def test_failed_task_shows_error_summary_and_next_action() -> None:
    task = presentation(
        status="任务失败（退出码 2）",
        output_text="[red]未生成可交付字幕[/red]",
        state=TaskState.FAILED,
        failed_stage="语音识别",
        error_message="模型文件损坏",
    )
    async with TaskApp(task).run_test(size=(90, 56)) as pilot:
        await pilot.pause()

        visible = "\n".join(
            str(widget.render()) for widget in pilot.app.screen.query(Static)
        )
        assert not list(pilot.app.screen.query(ProgressBar))
        assert "错误摘要" in visible
        assert "退出码 2" in visible
        assert "失败阶段：语音识别" in visible
        assert "模型文件损坏" in visible
        assert "下一步" in visible
        assert "新建字幕" in visible
        assert "重新运行" not in visible


async def test_failed_task_can_open_a_new_task_form(tmp_path, monkeypatch) -> None:
    from subtap.ui.v2.new_transcription import NewTranscriptionScreen

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    task = presentation(
        status="任务失败（退出码 2）",
        state=TaskState.FAILED,
        allowed_actions=("diagnostics", "new_task", "details"),
    )
    async with TaskApp(task).run_test(size=(90, 56)) as pilot:
        await pilot.pause()
        pilot.app.screen.action_new_task()
        await pilot.pause()

        assert isinstance(pilot.app.screen, NewTranscriptionScreen)


async def test_interrupted_task_does_not_promise_unverified_resume() -> None:
    task = presentation(status="任务已中断", state=TaskState.INTERRUPTED)
    async with TaskApp(task).run_test(size=(90, 56)) as pilot:
        await pilot.pause()

        visible = "\n".join(
            str(widget.render()) for widget in pilot.app.screen.query(Static)
        )
        assert "已中断" in visible
        assert "任务未完成" in visible
        assert "Resume" not in visible
        assert "新建任务" in visible
        assert "错误摘要" not in visible


def test_unknown_task_status_fails_fast() -> None:
    with pytest.raises(ValueError, match="Unknown task status"):
        TaskScreen(presentation(status="任务状态未知", state="unknown"))
