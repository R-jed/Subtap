"""Ticket 06: demo must run under an explicit local-only policy.

Contracts A–H verify that `subtap demo` constructs a local-only
ExternalProcessingPolicy before Pipeline construction, normalizes
config so user remote settings cannot widen the demo, and passes
explicit policy-derived arguments to RichRunner.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from typer.testing import CliRunner

from subtap.cli import app
from subtap.runtime.external_policy import build_policy

runner = CliRunner()


# ── FakePipeline (lightweight stand-in) ─────────────────────────────


class FakePipeline:
    """Lightweight Pipeline stand-in that preserves the constructor seam.

    Exposes config, workspace.root, external_policy, set_stage_plan,
    run_stage — enough for real RichRunner to execute the full stage loop.
    """

    def __init__(self, config, work_dir, external_policy=None):
        self.config = config
        self._work_dir = Path(work_dir)
        self._work_dir.mkdir(parents=True, exist_ok=True)
        self.workspace = SimpleNamespace(
            root=self._work_dir,
            ensure_dirs=lambda: self._work_dir.mkdir(parents=True, exist_ok=True),
        )
        self.external_policy = external_policy
        self._stage_calls: list = []
        self._output_dir: Path | None = None

    def set_stage_plan(self, keys, ctx=None):
        self._stage_calls.append(("set_stage_plan", keys, ctx))

    def publish_plan(self, keys):
        pass

    def run_stage(self, stage, **kwargs):
        self._stage_calls.append(("run_stage", stage, kwargs))
        if stage == "export":
            out = Path(kwargs.get("output_dir", "."))
            stem = kwargs.get("stem", "final")
            fmt = kwargs.get("fmt", "srt")
            path = out / f"{stem}.{fmt}"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nHello\n\n", encoding="utf-8"
            )
            return {"output_path": str(path)}
        return {
            "prepare": {"media_info": {"duration": 1.0, "sample_rate": 16000}},
            "chunk": {"chunk_count": 1},
            "asr": {"segment_count": 1},
            "clean": {"segment_count": 1},
            "segment": {"sentence_count": 1},
            "align": {"aligned_count": 1},
            "hotword": {"replaced": 0, "total": 1},
            "learn": {"learned": 0},
        }.get(stage, {})


# ── helpers ──────────────────────────────────────────────────────────


def _make_remote_config(**overrides):
    """Create a config with remote-oriented settings.

    Used as the default load_config return value for demo tests.
    The demo normalizes these to local-only values before execution.
    """
    base = SimpleNamespace(
        mode="online",
        asr=SimpleNamespace(backend="http-asr", model="asr_0.6b", hotwords=[]),
        llm_proofread=True,
        llm_hotword=True,
        clean=SimpleNamespace(backend="openai:gpt-4o-mini", glossary_path=""),
        translate_to="en",
        output=SimpleNamespace(
            subtitle_punctuation=False,
            subtitle_language="zh",
            max_chars=25,
            subtitle_formats=["srt"],
            subtitle_stem="final",
            script_path=None,
            script_mode="follow_script",
        ),
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def _setup_demo_env(monkeypatch, tmp_path, sample_name="demo.wav"):
    """Set up deterministic demo environment under tmp_path.

    Returns (synth_root, config_path).
    """
    synth_root = tmp_path / "repo"
    samples_dir = synth_root / "samples"
    samples_dir.mkdir(parents=True)
    (samples_dir / sample_name).write_bytes(b"fake-audio")

    # _demo() derives sample dir from __file__: parents[3] must == synth_root
    # Real path: repo/src/subtap/cli/pipeline_cli.py → parents[3] = repo
    monkeypatch.setattr(
        "subtap.cli.pipeline_cli.__file__",
        str(synth_root / "src" / "subtap" / "cli" / "pipeline_cli.py"),
    )

    # Isolate cwd so ./demo_work stays under tmp_path
    monkeypatch.chdir(tmp_path)

    return synth_root


# ── Contract A ───────────────────────────────────────────────────────


def test_demo_completes_with_policy(tmp_path, monkeypatch):
    """A. Demo creates Pipeline with external_policy, real RichRunner completes."""
    _setup_demo_env(monkeypatch, tmp_path)

    pipelines_built: list = []

    def _capture_pipeline(config, work_dir, external_policy=None):
        pipelines_built.append(SimpleNamespace(external_policy=external_policy))
        return FakePipeline(config, work_dir, external_policy=external_policy)

    with (
        patch("subtap.core.pipeline.Pipeline", side_effect=_capture_pipeline),
        patch(
            "subtap.schemas.config.load_config",
            return_value=_make_remote_config(),
        ),
    ):
        result = runner.invoke(app, ["demo"])

    assert result.exit_code == 0, f"Demo failed: {result.output}"
    assert len(pipelines_built) == 1

    policy = pipelines_built[0].external_policy
    assert policy is not None, "Pipeline must receive external_policy"
    assert policy.local_only is True
    assert policy.enhance_mode.value == "local"


# ── Contract B ───────────────────────────────────────────────────────


def test_demo_config_cannot_be_widened(tmp_path, monkeypatch):
    """B. Remote user config is normalized; demo remains local-only."""
    _setup_demo_env(monkeypatch, tmp_path)

    captured_config = {}
    captured_policy = {}

    def _spy_pipeline(config, work_dir, external_policy=None):
        captured_config["asr_backend"] = getattr(
            getattr(config, "asr", None), "backend", None
        )
        captured_config["llm_proofread"] = getattr(config, "llm_proofread", None)
        captured_config["llm_hotword"] = getattr(config, "llm_hotword", None)
        captured_policy["policy"] = external_policy
        return FakePipeline(config, work_dir, external_policy=external_policy)

    with (
        patch("subtap.core.pipeline.Pipeline", side_effect=_spy_pipeline),
        patch("subtap.schemas.config.load_config", return_value=_make_remote_config()),
    ):
        result = runner.invoke(app, ["demo"])

    assert result.exit_code == 0, f"Demo failed: {result.output}"

    # Config normalized to local demo values
    assert captured_config["asr_backend"] == "mlx-qwen-asr"
    assert captured_config["llm_proofread"] is False
    assert captured_config["llm_hotword"] is False

    # Policy is local-only
    policy = captured_policy["policy"]
    assert policy is not None
    assert policy.local_only is True
    assert policy.enhance_mode.value == "local"
    assert policy.remote_asr is False
    assert policy.llm_proofread is False
    assert policy.llm_hotword is False
    assert policy.translation is False
    assert policy.sends_audio is False
    assert policy.sends_text is False


# ── Contract C ───────────────────────────────────────────────────────


def test_demo_policy_identity(tmp_path, monkeypatch):
    """C. build_policy receives exact demo inputs; same object flows through."""
    _setup_demo_env(monkeypatch, tmp_path)

    captured = {}

    def _spy_build_policy(**kwargs):
        captured["kwargs"] = kwargs
        policy = build_policy(**kwargs)
        captured["policy"] = policy
        return policy

    def _spy_pipeline(config, work_dir, external_policy=None):
        captured["pipeline_policy"] = external_policy
        p = FakePipeline(config, work_dir, external_policy=external_policy)
        original_set_plan = p.set_stage_plan

        def _spy_set_plan(keys, ctx=None):
            if ctx is not None:
                captured["ctx"] = ctx
            original_set_plan(keys, ctx)

        p.set_stage_plan = _spy_set_plan
        return p

    with (
        patch("subtap.core.pipeline.Pipeline", side_effect=_spy_pipeline),
        patch("subtap.cli.pipeline_cli.build_policy", side_effect=_spy_build_policy),
        patch(
            "subtap.schemas.config.load_config",
            return_value=_make_remote_config(),
        ),
    ):
        result = runner.invoke(app, ["demo"])

    assert result.exit_code == 0, f"Demo failed: {result.output}"

    # Exact build_policy inputs
    assert captured["kwargs"]["local_only"] is True
    assert captured["kwargs"]["enhance_mode"] == "local"
    assert captured["kwargs"]["asr_backend"] == "mlx-qwen-asr"
    assert captured["kwargs"]["llm_proofread"] is False
    assert captured["kwargs"]["llm_hotword"] is False
    assert captured["kwargs"]["translation"] is False

    # Object identity
    assert captured["pipeline_policy"] is captured["policy"]

    # Context fields
    ctx = captured["ctx"]
    assert ctx.local_only is True
    assert ctx.policy_mode == "local"
    assert ctx.llm_proofread is False
    assert ctx.llm_hotword is False
    assert ctx.asr_backend == "mlx-qwen-asr"
    assert ctx.translate_to == ""


# ── Contract D ───────────────────────────────────────────────────────


def test_demo_explicit_runner_arguments(tmp_path, monkeypatch):
    """D. _demo() calls RichRunner with explicit policy-derived arguments."""
    _setup_demo_env(monkeypatch, tmp_path)

    runner_args = {}

    from subtap.ui.tui import RichRunner

    original_run_pipeline = RichRunner.run_pipeline

    def _spy_run_pipeline(self, pipeline, input_path, output_dir, **kwargs):
        runner_args["pipeline"] = pipeline
        runner_args["fmt"] = kwargs.get("fmt")
        runner_args["enhance"] = kwargs.get("enhance")
        runner_args["translate_to"] = kwargs.get("translate_to")
        runner_args["bilingual"] = kwargs.get("bilingual")
        return original_run_pipeline(self, pipeline, input_path, output_dir, **kwargs)

    with (
        patch(
            "subtap.core.pipeline.Pipeline",
            side_effect=lambda c, work_dir, external_policy=None: FakePipeline(
                c, work_dir, external_policy
            ),
        ),
        patch(
            "subtap.schemas.config.load_config",
            return_value=_make_remote_config(),
        ),
        patch.object(RichRunner, "run_pipeline", _spy_run_pipeline),
    ):
        result = runner.invoke(app, ["demo"])

    assert result.exit_code == 0, f"Demo failed: {result.output}"

    assert runner_args["fmt"] == "srt"
    assert runner_args["enhance"] == "local"
    assert runner_args["translate_to"] is None
    assert runner_args["bilingual"] == "off"
    assert runner_args["pipeline"].external_policy is not None


# ── Contract E ───────────────────────────────────────────────────────


def test_demo_no_external_disclosure(tmp_path, monkeypatch):
    """E. No external-processing disclosure lines appear in demo output."""
    _setup_demo_env(monkeypatch, tmp_path)

    captured_policy = {}

    def _spy_pipeline(config, work_dir, external_policy=None):
        captured_policy["policy"] = external_policy
        return FakePipeline(config, work_dir, external_policy=external_policy)

    with (
        patch("subtap.core.pipeline.Pipeline", side_effect=_spy_pipeline),
        patch(
            "subtap.schemas.config.load_config",
            return_value=_make_remote_config(),
        ),
    ):
        result = runner.invoke(app, ["demo"])

    assert result.exit_code == 0, f"Demo failed: {result.output}"

    # Assert on the actual policy object produced by _demo()
    policy = captured_policy["policy"]
    assert policy is not None
    assert policy.disclosure_lines() == []

    assert "⚠ 音频将发送至外部 ASR 服务进行识别。" not in result.output
    assert "⚠ 字幕文本将发送至外部 LLM 服务进行处理。" not in result.output


# ── Contract F ───────────────────────────────────────────────────────


def test_demo_no_first_run_wizard(tmp_path, monkeypatch):
    """F. Demo does not invoke check_first_run_wizard."""
    _setup_demo_env(monkeypatch, tmp_path)

    wizard_calls: list = []

    def _fail_wizard(*_args, **_kwargs):
        wizard_calls.append(True)
        return False

    with (
        patch(
            "subtap.core.pipeline.Pipeline",
            side_effect=lambda c, work_dir, external_policy=None: FakePipeline(
                c, work_dir, external_policy
            ),
        ),
        patch(
            "subtap.schemas.config.load_config",
            return_value=_make_remote_config(),
        ),
        patch(
            "subtap.cli.pipeline_cli.check_first_run_wizard", side_effect=_fail_wizard
        ),
    ):
        result = runner.invoke(app, ["demo"])

    assert result.exit_code == 0, f"Demo failed: {result.output}"
    assert len(wizard_calls) == 0, "check_first_run_wizard must not be called for demo"


# ── Contract G ───────────────────────────────────────────────────────


def test_demo_missing_sample_early_exit(tmp_path, monkeypatch):
    """G. Missing samples exits before load_config, build_policy, Pipeline, or RichRunner."""
    synth_root = tmp_path / "repo"
    empty_samples = synth_root / "samples"
    empty_samples.mkdir(parents=True)
    # No files in samples/

    monkeypatch.setattr(
        "subtap.cli.pipeline_cli.__file__",
        str(synth_root / "src" / "cli" / "pipeline_cli.py"),
    )
    monkeypatch.chdir(tmp_path)

    config_calls: list = []
    policy_calls: list = []
    pipeline_calls: list = []
    rich_calls: list = []

    def _spy_config(*_a, **_kw):
        config_calls.append(True)
        return SimpleNamespace()

    def _spy_policy(**_kw):
        policy_calls.append(True)
        return build_policy(local_only=True, enhance_mode="local")

    def _spy_pipeline(*_a, **_kw):
        pipeline_calls.append(True)
        return FakePipeline(SimpleNamespace(), tmp_path)

    from subtap.ui.tui import RichRunner as RealRichRunner

    def _spy_rich(*_a, **_kw):
        rich_calls.append(True)
        return RealRichRunner()

    with (
        patch("subtap.schemas.config.load_config", side_effect=_spy_config),
        patch("subtap.cli.pipeline_cli.build_policy", side_effect=_spy_policy),
        patch("subtap.core.pipeline.Pipeline", side_effect=_spy_pipeline),
        patch("subtap.ui.tui.RichRunner", side_effect=_spy_rich),
    ):
        result = runner.invoke(app, ["demo"])

    assert result.exit_code == 1
    assert (
        len(config_calls) == 0
    ), "load_config must not be called when samples are missing"
    assert (
        len(policy_calls) == 0
    ), "build_policy must not be called when samples are missing"
    assert (
        len(pipeline_calls) == 0
    ), "Pipeline must not be constructed when samples are missing"
    assert (
        len(rich_calls) == 0
    ), "RichRunner must not be constructed when samples are missing"


# ── Contract H ───────────────────────────────────────────────────────


def test_demo_local_only_help():
    """H. Demo help states local execution and no external API calls."""
    result = runner.invoke(app, ["demo", "--help"])

    assert result.exit_code == 0
    assert "默认本地" in result.output
    assert "final.srt" in result.output
    assert "不调用 LLM API" in result.output
