"""Smoke offline script behavior tests."""

from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import sys
import threading

import pytest


def test_smoke_offline_script_exists():
    script = Path("scripts/smoke_offline.sh")
    assert script.exists(), "smoke_offline.sh 不存在"
    assert script.stat().st_mode & 0o111, "脚本不可执行"


def test_smoke_offline_uses_isolated_home():
    script = Path("scripts/smoke_offline.sh").read_text()
    assert "mktemp" in script, "脚本必须使用临时目录"
    assert "SMOKE_HOME" in script, "脚本必须设置隔离 HOME"


def test_smoke_offline_disables_network():
    script = Path("scripts/smoke_offline.sh").read_text()
    assert "sandbox-exec" in script, "脚本必须由 macOS sandbox 拒绝网络访问"
    assert "(deny network*)" in script


def test_smoke_offline_checks_srt_delivery():
    script = Path("scripts/smoke_offline.sh").read_text()
    assert "check_srt_delivery" in script, "脚本必须检查 SRT 交付"


def test_smoke_offline_checks_reviewed_subtitle_regression():
    script = Path("scripts/smoke_offline.sh").read_text()

    assert "SUBTAP_SMOKE_REFERENCE_SRT" in script
    assert "check_srt_regression.py" in script


def test_smoke_offline_checks_performance_regression():
    script = Path("scripts/smoke_offline.sh").read_text()

    assert 'MAX_RTF="0.25"' in script
    assert "SUBTAP_SMOKE_MAX_RTF" not in script
    assert "check_performance.py" in script


def test_smoke_offline_runs_1_7b_high_quality_chinese_sample():
    script = Path("scripts/smoke_offline.sh").read_text()

    assert "asr_1.7b" in script
    assert "高质量中文语音.mp3" in script


def test_smoke_offline_accepts_json_output():
    script = Path("scripts/smoke_offline.sh").read_text()
    assert "JSON" in script or "json" in script, "脚本应支持 JSON 输出"


def test_smoke_offline_accepts_installed_subtap_binary():
    script = Path("scripts/smoke_offline.sh").read_text()

    assert "SUBTAP_SMOKE_SUBTAP_BIN" in script


@pytest.mark.skipif(shutil.which("sandbox-exec") is None, reason="requires macOS")
def test_smoke_offline_executes_all_samples_without_network(tmp_path):
    """Exercise the public smoke script with an installed-binary stand-in."""
    audio_dir = tmp_path / "audio"
    model_root = tmp_path / "models"
    audio_dir.mkdir()
    for filename in ("数字测试.mp3", "短的演讲音频.wav", "高质量中文语音.mp3"):
        (audio_dir / filename).touch()
    for model in ("asr_1.7b", "aligner"):
        model_dir = model_root / model
        model_dir.mkdir(parents=True)
        (model_dir / "config.json").write_text("{}", encoding="utf-8")

    calls = tmp_path / "calls.log"
    reviewed = tmp_path / "reviewed.srt"
    reviewed.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\n测试字幕\n",
        encoding="utf-8",
    )
    required = tmp_path / "required.txt"
    required.write_text("测试字幕\n", encoding="utf-8")

    class ProbeHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(204)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    probe = ThreadingHTTPServer(("127.0.0.1", 0), ProbeHandler)
    probe_thread = threading.Thread(target=probe.serve_forever, daemon=True)
    probe_thread.start()

    fake_subtap = tmp_path / "subtap"
    fake_subtap.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
grep -q '^GR4$' "$HOME/.subtap/glossaries/default.txt"
if /usr/bin/curl --noproxy '*' --silent --max-time 1 "$PROBE_URL" >/dev/null 2>&1; then
    exit 97
fi
printf '%s\\n' "$*" >> "$CALL_LOG"
output_dir=""
work_dir=""
while [[ $# -gt 0 ]]; do
    if [[ "$1" == "--output-dir" ]]; then
        shift
        output_dir="$1"
    elif [[ "$1" == "--work-dir" ]]; then
        shift
        work_dir="$1"
    fi
    shift
done
mkdir -p "$output_dir" "$work_dir"
printf '1\\n00:00:00,000 --> 00:00:01,000\\n测试字幕\\n' > "$output_dir/result.srt"
printf '{"metrics_schema_version":2,"audio_duration_sec":100.0,"total_runtime_sec":18.0,"rtf":0.18,"asr_runtime_sec":12.0,"align_runtime_sec":4.0,"asr_model_load_time_sec":2.0,"aligner_model_load_time_sec":1.0}\\n' > "$work_dir/metrics.json"
""",
        encoding="utf-8",
    )
    fake_subtap.chmod(0o755)

    try:
        result = subprocess.run(
            ["./scripts/smoke_offline.sh"],
            cwd=Path(__file__).parents[1],
            env={
                **os.environ,
                "ALL_PROXY": "",
                "CALL_LOG": str(calls),
                "HTTP_PROXY": "",
                "HTTPS_PROXY": "",
                "PROBE_URL": f"http://127.0.0.1:{probe.server_port}",
                "SUBTAP_SMOKE_AUDIO_DIR": str(audio_dir),
                "SUBTAP_SMOKE_MODEL_ROOT": str(model_root),
                "SUBTAP_SMOKE_REFERENCE_SRT": str(reviewed),
                "SUBTAP_SMOKE_REQUIRED_CUES": str(required),
                "SUBTAP_SMOKE_SUBTAP_BIN": str(fake_subtap),
                "SUBTAP_SMOKE_PYTHON_BIN": sys.executable,
            },
            text=True,
            capture_output=True,
            check=False,
        )
    finally:
        probe.shutdown()
        probe.server_close()
        probe_thread.join()

    assert result.returncode == 0, result.stderr
    invocations = calls.read_text(encoding="utf-8").splitlines()
    assert len(invocations) == 3
    assert all("--local-only" in invocation for invocation in invocations)
    assert any("高质量中文语音.mp3" in invocation for invocation in invocations)
    assert "CER=0.0000" in result.stdout
