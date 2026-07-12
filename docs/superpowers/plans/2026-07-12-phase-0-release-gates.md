# 阶段 0：恢复发布门禁实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 让本地验证与 CI 对同一份真实状态给出一致结论，并恢复 README、格式、Doctor 和发布前检查的绿色门禁。

**架构：** 不改字幕 pipeline。先恢复现有格式和 README 契约，再让 Doctor 只把当前配置选择的模型作为失败条件，同时保留全部模型的展示信息；最后用一个本地脚本承载与 CI 相同的快速验证。Homebrew 冷安装属于阶段 1，不在本计划中伪造通过状态。

**技术栈：** Python 3.12+、Typer、Pydantic、pytest、Black、mypy、Hatchling、GitHub Actions、POSIX shell。

---

## 文件结构

- 修改：`README.md` — 面向普通用户的真实安装边界、核心命令和开发状态。
- 修改：`src/subtap/backends/align/mlx_qwen_align.py` — 仅应用 Black 格式，不改变行为。
- 修改：`src/subtap/cli/doctor_cli.py` — 统一 Doctor 的模型判定与 workspace JSON 组合结果。
- 创建：`tests/test_doctor_release.py` — release Doctor 当前模型、可选模型与组合模式回归。
- 创建：`scripts/check.sh` — 本地与 CI 共用的验证入口。
- 修改：`.github/workflows/ci.yml` — 调用统一验证入口。
- 修改：`.github/workflows/release.yml` — 发布测试 job 调用同一验证入口。
- 修改：`.gitignore` — 明确忽略 macOS 元数据；不隐藏其他环境卫生问题。

## 范围边界

- 本计划不实现 Homebrew Formula/Cask，不声称 `brew install subtap` 已可用。
- 本计划不增加覆盖率上传服务。
- 本计划不修改 Pydantic Schema。
- 本计划不删除未合并的 `feat/swift-native-app`。
- `feat/segmentation-improvement` 已合并，可在所有验证通过后删除本地分支。

### 任务 1：恢复格式与 README 契约

**文件：**
- 修改：`README.md`
- 修改：`src/subtap/backends/align/mlx_qwen_align.py`
- 测试：`tests/test_readme_commands_match_cli.py`

- [ ] **步骤 1：运行现有失败检查，确认红灯**

运行：

```bash
uv run black --check src tests
uv run pytest -q tests/test_readme_commands_match_cli.py
```

预期：Black 报告 `mlx_qwen_align.py` 需要格式化；README 测试因缺少 `subtap run` 失败。

- [ ] **步骤 2：只格式化当前失败文件**

运行：

```bash
uv run black src/subtap/backends/align/mlx_qwen_align.py
git diff -- src/subtap/backends/align/mlx_qwen_align.py
```

预期：diff 只有格式变化，Fail Fast 行为和异常文案不变。

- [ ] **步骤 3：补齐普通用户 README**

将 README 保持在当前真实能力范围，至少包含：

````markdown
## 支持范围

Subtap 当前支持 Apple Silicon Mac，使用 MLX 在本地生成字幕。项目仍处于开发阶段，Homebrew 正式分发尚未完成。

## 开发环境使用

```bash
uv sync --extra dev
uv run subtap setup
uv run subtap doctor
uv run subtap run input.mp3 --mode quality --enhance local --local-only
```

## 常用命令

- `subtap run`：运行完整字幕流程
- `subtap setup`：初始化配置与模型
- `subtap doctor`：检查本地环境
- `subtap demo`：运行演示
- `subtap glossary`：管理热词
- `subtap learn`：学习人工修正
- `subtap profile`：查看本地学习档案
````

不得写入尚不可用的 `brew install subtap`，不得承诺 Intel、Linux、DirectML、Vulkan 或第三方 ASR。

- [ ] **步骤 4：验证 README 与格式检查通过**

运行：

```bash
uv run black --check src tests
uv run pytest -q tests/test_readme_commands_match_cli.py
```

预期：两条命令均通过。

- [ ] **步骤 5：Commit**

```bash
git add README.md src/subtap/backends/align/mlx_qwen_align.py
git commit -m "docs: 恢复用户入口与格式门禁"
```

### 任务 2：Doctor 只校验当前运行所需模型

**文件：**
- 修改：`src/subtap/cli/doctor_cli.py`
- 创建：`tests/test_doctor_release.py`

- [ ] **步骤 1：编写当前模型完整、可选模型缺失的失败测试**

```python
def test_release_doctor_ignores_unselected_optional_asr(monkeypatch, tmp_path):
    config = make_config(asr_model="asr_1.7b", aligner_model="aligner")
    install_model(tmp_path, "asr_1.7b")
    install_model(tmp_path, "aligner")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr("subtap.schemas.config.load_config", lambda _: config)
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/tool")

    result = CliRunner().invoke(app, ["doctor", "--release", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    optional = next(m for m in payload["models"] if m["name"] == "asr_0.6b")
    assert optional["required"] is False
    assert optional["installed"] is False
```

测试辅助函数 `make_config` 返回包含 `asr`、`align`、`remote_api` 的 `SimpleNamespace`；`install_model` 根据 `MODEL_REGISTRY[name]["required_files"]` 在 `tmp_path/.subtap/models/<subdir>` 创建非空文件。

- [ ] **步骤 2：编写当前选择模型缺失的失败测试**

```python
def test_release_doctor_fails_when_selected_model_is_missing(monkeypatch, tmp_path):
    config = make_config(asr_model="asr_1.7b", aligner_model="aligner")
    install_model(tmp_path, "aligner")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr("subtap.schemas.config.load_config", lambda _: config)
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/tool")

    result = CliRunner().invoke(app, ["doctor", "--release", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    selected = next(m for m in payload["models"] if m["name"] == "asr_1.7b")
    assert selected["required"] is True
    assert selected["installed"] is False
```

- [ ] **步骤 3：运行测试验证失败**

运行：

```bash
uv run pytest -q tests/test_doctor_release.py
```

预期：FAIL；当前 Doctor 要求全部 registry 模型完整，并且报告中没有 `required`。

- [ ] **步骤 4：在 Doctor 报告层区分 required 与 optional**

在读取配置后建立唯一必需集合：

```python
required_models = {config.asr.model, config.align.model}
```

生成每个模型报告时增加字段，并只让必需模型影响 `all_ok`：

```python
required = ms.name in required_models
report["models"].append(
    {
        "name": ms.name,
        "required": required,
        "installed": ms.installed,
        "path": str(ms.path),
        "missing_files": ms.missing_files,
    }
)
if required and not ms.installed:
    all_ok = False
```

全部 registry 模型仍显示，避免用户误以为可选模型不存在；只有当前配置需要的模型决定 release Doctor 成败。

- [ ] **步骤 5：验证 Doctor 模型测试**

运行：

```bash
uv run pytest -q tests/test_doctor_release.py tests/test_doctor_model_panel.py tests/test_doctor_panel.py
```

预期：全部通过。

- [ ] **步骤 6：Commit**

```bash
git add src/subtap/cli/doctor_cli.py tests/test_doctor_release.py
git commit -m "fix: Doctor 只校验当前模型"
```

### 任务 3：让 workspace Doctor 可组合且可机器读取

**文件：**
- 修改：`src/subtap/cli/doctor_cli.py`
- 修改：`tests/test_doctor_release.py`

- [ ] **步骤 1：编写组合模式失败测试**

```python
def test_doctor_combines_release_and_workspace_json(monkeypatch, tmp_path):
    configure_complete_release_environment(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app, ["doctor", "--release", "--workspace", "--json"]
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["release"] is True
    assert "workspace_status" in payload
    assert "checks" in payload
    assert "models" in payload
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```bash
uv run pytest -q tests/test_doctor_release.py::test_doctor_combines_release_and_workspace_json
```

预期：FAIL；当前 `workspace` 分支提前打印并 `return`，输出不是 JSON，也没有 release 结果。

- [ ] **步骤 3：把 workspace 检查改为返回数据**

将 `_doctor_workspace` 改为纯收集函数，返回结构化数据：

```python
def _collect_workspace_status(work_dir: Path = Path("./work")) -> dict[str, Any]:
    git_guard = GitGuard(work_dir)
    cleanroom = Cleanroom(work_dir)
    git_status = git_guard.get_git_status()
    return {
        "git": {
            "is_repo": git_guard.is_git_repo(),
            "branch": git_status["branch"],
            "dirty": git_status["is_dirty"],
            "changed_files": git_status["changed_files"],
        },
        "cleanroom": cleanroom.check_workspace(),
        "pipeline_files": {
            name: (work_dir / name).exists()
            for name in (
                "chunks/chunks.jsonl",
                "asr/asr.jsonl",
                "cleaned.jsonl",
                "sentences.jsonl",
                "aligned.jsonl",
            )
        },
    }
```

保留单独的 `_render_workspace_status(status)` 负责现有文本 UI。`--json` 不调用 renderer。

- [ ] **步骤 4：组合而不是提前返回**

Doctor 开始时收集：

```python
workspace_status = _collect_workspace_status() if workspace else None
```

标准 report 增加：

```python
if workspace_status is not None:
    report["workspace_status"] = workspace_status
```

仅当命令是 `doctor --workspace` 且没有 `--release`、没有 `--json` 时渲染工作区文本并返回；其他组合继续执行完整 Doctor。

- [ ] **步骤 5：验证所有 Doctor 模式**

运行：

```bash
uv run pytest -q tests/test_doctor_release.py tests/test_doctor_model_panel.py tests/test_doctor_panel.py
```

预期：普通、release、workspace、JSON 和组合模式全部通过。

- [ ] **步骤 6：Commit**

```bash
git add src/subtap/cli/doctor_cli.py tests/test_doctor_release.py
git commit -m "fix: 统一 Doctor 组合检查结果"
```

### 任务 4：建立本地与 CI 单一验证入口

**文件：**
- 创建：`scripts/check.sh`
- 修改：`.github/workflows/ci.yml`
- 修改：`.github/workflows/release.yml`
- 修改：`.gitignore`

- [ ] **步骤 1：创建失败即停止的验证脚本**

```bash
#!/usr/bin/env bash
set -euo pipefail

uv run black --check src tests
uv run mypy src/subtap
uv run pytest -q -p no:cacheprovider

rm -rf dist
uv build
uv run pytest -q tests/test_release_packaging.py
```

`dist` 是仓库根目录下的固定构建产物。脚本开始时先用 `git rev-parse --show-toplevel` 确认当前目录就是仓库根目录，再执行删除；不得把路径改成环境变量或用户输入。

脚本不运行模型下载或完整 1.7B pipeline；这些属于发布验收而不是每次提交的快速门禁。

- [ ] **步骤 2：让 CI 调用同一脚本**

在 CI 与 release 的测试 job 中，用以下单一步骤替换重复的格式、类型、pytest、build 和 packaging 命令：

```yaml
- name: Verify source and package
  run: ./scripts/check.sh
```

保留 wheel 独立环境 smoke test。release 的 Homebrew job 不在本任务中宣称通过，只保留现有流程等待阶段 1 重做。

- [ ] **步骤 3：补齐 macOS 元数据忽略规则**

确保 `.gitignore` 包含：

```gitignore
.DS_Store
**/.DS_Store
```

然后只删除仓库内未跟踪的 `.DS_Store`；不得删除构建目录中的其他文件，不得修改用户目录。

- [ ] **步骤 4：验证本地入口**

运行：

```bash
chmod +x scripts/check.sh
./scripts/check.sh
```

预期：所有步骤通过，生成 wheel 和 sdist，release packaging 测试通过。

- [ ] **步骤 5：核对 workflow 语法与差异**

运行：

```bash
uv run python - <<'PY'
from pathlib import Path
import yaml

for path in (Path(".github/workflows/ci.yml"), Path(".github/workflows/release.yml")):
    yaml.safe_load(path.read_text(encoding="utf-8"))
    print(f"ok: {path}")
PY
git diff --check
```

预期：两个 workflow 可解析，diff 无空白错误。

- [ ] **步骤 6：Commit**

```bash
git add scripts/check.sh .github/workflows/ci.yml .github/workflows/release.yml .gitignore
git commit -m "ci: 统一本地与发布验证入口"
```

### 任务 5：最终验证与分支卫生

**文件：**
- 不新增代码文件

- [ ] **步骤 1：运行统一验证入口**

```bash
./scripts/check.sh
```

预期：格式、mypy、全量测试、构建和 packaging 全部通过。

- [ ] **步骤 2：运行本机只读 Doctor**

```bash
uv run subtap doctor --release --workspace --json
```

预期：输出单个合法 JSON；当前选择的 1.7B 与 aligner 完整时 `ok=true`，未安装的 0.6B 标记为 `required=false`。

- [ ] **步骤 3：确认真实 pipeline 证据仍有效**

检查现有最终验收文件，不重新跑模型：

```bash
test -s "/Users/qunqing/Downloads/ASR-SRT测试音频/subtap-semantic-boundaries-final-v3/output/高质量中文语音.srt"
```

预期：文件存在且非空。若本阶段改动意外触及 pipeline 文件，则必须重新运行完整 1.7B pipeline；否则不浪费模型执行时间。

- [ ] **步骤 4：完成双轴代码审查**

以本计划开始前的固定提交为基准执行 Standards 与 Spec review。必须确认：

- README 没有声称 Homebrew 已可用；
- release Doctor 只要求当前选择模型；
- workspace JSON 可组合；
- CI 与本地执行同一验证脚本；
- 没有修改字幕 pipeline 行为。

- [ ] **步骤 5：清理已合并分支**

先确认祖先关系：

```bash
git merge-base --is-ancestor feat/segmentation-improvement main
```

命令成功后删除本地已合并分支：

```bash
git branch -d feat/segmentation-improvement
```

不得删除 `feat/swift-native-app`，因为它尚未合并。

- [ ] **步骤 6：记录最终状态**

```bash
git status --short --branch
git log -5 --oneline
```

预期：工作树干净；所有阶段 0 提交位于 `main`；未经用户明确授权不推送远端。

## 后续独立计划

阶段 0 完成后再分别编写并执行：

1. Apple Silicon Homebrew 冷安装与发布完整性计划。
2. `~/.subtap` 统一资源目录与安全迁移计划。
3. 模型下载、热词库和文稿库管理计划。
4. Textual TUI 首次启动与新建字幕向导计划。

这些计划不能与阶段 0 合并提交，避免发布基础、数据迁移和 UI 重构互相遮蔽。
