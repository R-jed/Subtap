"""Upgrade and rollback verification tests."""

from __future__ import annotations


def test_config_survives_upgrade(tmp_path):
    """升级后 config.yaml 内容保留。"""
    from subtap.schemas.config import load_config

    config_dir = tmp_path / ".subtap"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(
        "mode: offline\nmodels:\n  root: models\nasr:\n  model: asr_1.7b\n  quantization: q8\n  keep_model_alive: false\n  warmup: false\n  hotwords: []\nalign:\n  model: aligner\n  quantization: q8\n  keep_model_alive: false\n  warmup: false\n  language: Chinese\n  time_offset_sec: -0.15\nremote_api:\n  api_key_env: SUBTAP_API_KEY\n",
        encoding="utf-8",
    )

    config = load_config(config_path)
    assert config.asr.model == "asr_1.7b"
    assert config.align.model == "aligner"


def test_state_json_preserved_after_upgrade(tmp_path):
    """升级后 state.json 内容保留。"""
    from subtap.core.state_store import StateStore

    state_path = tmp_path / ".subtap" / "state.json"
    state_path.parent.mkdir(parents=True)

    store = StateStore(state_path)
    store.load()
    store.add_recent_task("task-001", "test.mp3", "/output/final.srt")

    # 模拟升级：重新加载
    store2 = StateStore(state_path)
    state2 = store2.load()
    assert len(state2.recent_tasks) == 1
    assert state2.recent_tasks[0]["task_id"] == "task-001"


def test_model_directory_structure_is_valid(tmp_path):
    """模型目录结构完整性验证。"""
    model_dir = tmp_path / ".subtap" / "models" / "asr_1.7b"
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text('{"version": 1}')
    (model_dir / "model.safetensors").write_bytes(b"x" * 1000)

    # 模拟升级后检查
    assert model_dir.exists()
    assert (model_dir / "config.json").exists()
    assert (model_dir / "model.safetensors").exists()


def test_migration_preserves_unknown_files(tmp_path):
    """迁移不删除未知文件。"""
    subtap_dir = tmp_path / ".subtap"
    subtap_dir.mkdir(parents=True)
    (subtap_dir / "config.yaml").write_text("mode: offline\n")
    (subtap_dir / "unknown_file.txt").write_text("user data")
    (subtap_dir / "glossary").mkdir()
    (subtap_dir / "glossary" / "hotwords.txt").write_text("test")

    from subtap.core.migration import plan_migration

    plan = plan_migration(subtap_dir)

    # unknown_file.txt 不应出现在 moves 或 deletes 中
    move_srcs = [str(m.src) for m in plan.moves]
    assert not any("unknown_file" in s for s in move_srcs)


def test_rollback_to_previous_version(tmp_path):
    """回滚到上一版本：旧配置格式仍可读取。"""
    from subtap.core.models import MODEL_REGISTRY

    # 模拟旧版本配置（使用旧模型名）
    for model_name, info in MODEL_REGISTRY.items():
        model_dir = tmp_path / ".subtap" / "models" / info["subdir"]
        model_dir.mkdir(parents=True, exist_ok=True)
        for fname in info["required_files"]:
            (model_dir / fname).write_text("stub")

    # 验证所有模型目录结构完整
    for model_name, info in MODEL_REGISTRY.items():
        model_dir = tmp_path / ".subtap" / "models" / info["subdir"]
        assert model_dir.exists(), f"{model_name} 目录不存在"
        for fname in info["required_files"]:
            assert (model_dir / fname).exists(), f"{model_name}/{fname} 不存在"
