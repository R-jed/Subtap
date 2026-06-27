# 开发版验收修复实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 修复七维验收报告中影响“macOS 开发版源码安装”真实验收的硬问题：模型路径统一、模型下载向导、doctor 真实失败、setup 去假承诺、CLI 模块入口、文档对齐。

**架构：** 模型统一放在项目根目录 `models/`，模型安装由 `SetupWizard` 编排，`ModelDownloader` 负责来源选择、连通性探测、stdlib 下载和 Rich 进度显示。`doctor --release` 使用同一套模型 registry 校验，缺失即失败。

**技术栈：** Python stdlib `urllib.request`、`urllib.parse`、`ssl`、`time`、`pathlib`；已有依赖 `rich`、`typer`、`pydantic`、`pytest`。不新增 `huggingface_hub`、`modelscope` 等默认依赖。

---

## 文件结构

- 修改：`src/subtap/core/models.py`
  - 统一模型 manifest、项目内模型根目录、下载源、连通性探测、文件下载、校验。
- 修改：`src/subtap/core/setup.py`
  - 实现交互式模型下载选择、默认联网下载向导、失败降级选择、非交互参数路径。
- 修改：`src/subtap/cli.py`
  - 调整 `setup` 参数，修复 `doctor --release` 真实失败，补 `python -m subtap.cli` 入口。
- 修改：`src/subtap/schemas/config.py`
  - 默认 `models.root` 改为项目内 `models`。
- 修改：`configs/default.yaml`
  - 同步 `models.root: models` 和下载源配置。
- 修改：`tests/test_models.py`
  - 覆盖模型路径、下载 URL、连通性失败、stdlib 下载进度回调、校验。
- 修改：`tests/test_setup.py`
  - 覆盖 setup 交互选择、跳过下载、HF 失败降级到镜像、manual 校验。
- 修改：`tests/test_cli.py`
  - 覆盖 `doctor --release` 缺模型失败、`python -m subtap.cli --help` 输出、setup 参数。
- 修改：`README.md`
  - 明确 macOS 开发版、项目内 `models/`、四种安装方式、默认镜像 `https://hf-mirror.com`、无 Homebrew 承诺。
- 修改：`RELEASE.md`
  - 改为开发版真实能力说明。
- 修改：`scripts/release-check.sh`
  - 改为开发版检查，不要求真实下载模型，不误报 release-ready。

## 任务 1：统一模型 manifest 和项目内路径

**文件：**
- 修改：`src/subtap/core/models.py:15-33`
- 修改：`src/subtap/schemas/config.py:51-55`
- 修改：`configs/default.yaml`
- 测试：`tests/test_models.py`

- [ ] **步骤 1：编写失败测试**

在 `tests/test_models.py` 增加：

```python
def test_default_model_root_is_project_models():
    from subtap.schemas.config import SubtapConfig
    from subtap.core.models import _get_model_root

    root = _get_model_root(SubtapConfig())

    assert root.name == "models"
    assert root.parent == Path(__file__).resolve().parent.parent


def test_registry_uses_development_model_names():
    from subtap.core.models import MODEL_REGISTRY

    assert MODEL_REGISTRY["asr_0.6b"]["subdir"] == "asr_0.6b"
    assert MODEL_REGISTRY["asr_1.7b"]["subdir"] == "asr_1.7b"
    assert MODEL_REGISTRY["aligner"]["subdir"] == "aligner"
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```bash
.venv/bin/python -m pytest tests/test_models.py::test_default_model_root_is_project_models tests/test_models.py::test_registry_uses_development_model_names -q
```

预期：至少一个测试失败，原因是当前默认根目录或 registry 名称仍是旧口径。

- [ ] **步骤 3：实现最少代码**

在 `src/subtap/core/models.py` 中：

```python
PROJECT_ROOT = Path(__file__).resolve().parents[2]

MODEL_REGISTRY: dict[str, dict] = {
    "asr_0.6b": {
        "description": "Qwen3 ASR 0.6B MLX 8bit",
        "subdir": "asr_0.6b",
        "required_files": ["config.json", "model.safetensors"],
        "hf_repo": "aufklarer/Qwen3-ASR-0.6B-MLX-8bit",
        "modelscope_repo": "",
    },
    "asr_1.7b": {
        "description": "Qwen3 ASR 1.7B MLX 8bit",
        "subdir": "asr_1.7b",
        "required_files": ["config.json", "model.safetensors"],
        "hf_repo": "aufklarer/Qwen3-ASR-1.7B-MLX-8bit",
        "modelscope_repo": "",
    },
    "aligner": {
        "description": "Qwen3 ForcedAligner 0.6B MLX 8bit",
        "subdir": "aligner",
        "required_files": ["config.json", "model.safetensors"],
        "hf_repo": "mlx-community/Qwen3-ForcedAligner-0.6B-8bit",
        "modelscope_repo": "",
    },
}


def _get_model_root(config: SubtapConfig) -> Path:
    root = Path(config.models.root).expanduser()
    return root if root.is_absolute() else PROJECT_ROOT / root
```

在 `src/subtap/schemas/config.py` 中：

```python
class ModelConfig(BaseModel):
    """Model management configuration."""

    root: str = "models"
    auto_download: bool = False
    hf_endpoint: str = "https://huggingface.co"
    hf_mirror_endpoint: str = "https://hf-mirror.com"
```

在 `configs/default.yaml` 中同步：

```yaml
models:
  root: models
  auto_download: false
  hf_endpoint: https://huggingface.co
  hf_mirror_endpoint: https://hf-mirror.com
```

- [ ] **步骤 4：运行测试验证通过**

运行：

```bash
.venv/bin/python -m pytest tests/test_models.py::test_default_model_root_is_project_models tests/test_models.py::test_registry_uses_development_model_names -q
```

预期：2 passed。

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/core/models.py src/subtap/schemas/config.py configs/default.yaml tests/test_models.py
git commit -m "fix: 统一开发版模型目录"
```

## 任务 2：stdlib 下载器、连通性探测和 Rich 进度

**文件：**
- 修改：`src/subtap/core/models.py:97-127`
- 测试：`tests/test_models.py`

- [ ] **步骤 1：编写失败测试**

在 `tests/test_models.py` 增加：

```python
def test_downloader_builds_hf_file_url(tmp_path):
    from subtap.core.models import ModelDownloader
    from subtap.schemas.config import SubtapConfig

    cfg = SubtapConfig()
    cfg.models.root = str(tmp_path / "models")
    downloader = ModelDownloader(cfg)

    url = downloader.build_file_url(
        source="hf",
        repo="owner/model",
        filename="config.json",
    )

    assert url == "https://huggingface.co/owner/model/resolve/main/config.json"


def test_downloader_builds_hf_mirror_file_url(tmp_path):
    from subtap.core.models import ModelDownloader
    from subtap.schemas.config import SubtapConfig

    cfg = SubtapConfig()
    cfg.models.root = str(tmp_path / "models")
    cfg.models.hf_mirror_endpoint = "https://hf-mirror.com"
    downloader = ModelDownloader(cfg)

    url = downloader.build_file_url(
        source="hf-mirror",
        repo="owner/model",
        filename="model.safetensors",
    )

    assert url == "https://hf-mirror.com/owner/model/resolve/main/model.safetensors"


def test_downloader_rejects_modelscope_without_repo(tmp_path):
    from subtap.core.models import ModelDownloader
    from subtap.schemas.config import SubtapConfig

    cfg = SubtapConfig()
    cfg.models.root = str(tmp_path / "models")
    downloader = ModelDownloader(cfg)

    try:
        downloader.download("asr_0.6b", source="modelscope")
    except ValueError as exc:
        assert "ModelScope" in str(exc)
    else:
        raise AssertionError("ModelScope repo 缺失时必须失败")
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```bash
.venv/bin/python -m pytest tests/test_models.py::test_downloader_builds_hf_file_url tests/test_models.py::test_downloader_builds_hf_mirror_file_url tests/test_models.py::test_downloader_rejects_modelscope_without_repo -q
```

预期：失败，原因是 `build_file_url()` 或 `source` 参数尚不存在。

- [ ] **步骤 3：实现最少代码**

在 `ModelDownloader` 中加入：

```python
DEFAULT_TIMEOUT = 5


def _clean_endpoint(value: str) -> str:
    return value.rstrip("/")


class ModelDownloader:
    def __init__(self, config: SubtapConfig):
        self.config = config
        self.root = _get_model_root(config)

    def build_file_url(self, source: str, repo: str, filename: str) -> str:
        if source == "hf":
            endpoint = _clean_endpoint(self.config.models.hf_endpoint)
            return f"{endpoint}/{repo}/resolve/main/{filename}"
        if source == "hf-mirror":
            endpoint = _clean_endpoint(self.config.models.hf_mirror_endpoint)
            return f"{endpoint}/{repo}/resolve/main/{filename}"
        if source == "modelscope":
            return f"https://modelscope.cn/models/{repo}/resolve/master/{filename}"
        raise ValueError(f"未知下载源：{source}")

    def check_connectivity(self, source: str, repo: str) -> bool:
        import urllib.request

        filename = "config.json"
        url = self.build_file_url(source, repo, filename)
        request = urllib.request.Request(url, method="HEAD")
        try:
            with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
                return 200 <= response.status < 400
        except Exception:
            return False

    def download(self, model_name: str, source: str = "hf", progress=None) -> Path:
        if model_name not in MODEL_REGISTRY:
            raise ValueError(f"未知模型：{model_name}")

        info = MODEL_REGISTRY[model_name]
        repo_key = "modelscope_repo" if source == "modelscope" else "hf_repo"
        repo = info.get(repo_key) or ""
        if not repo:
            raise ValueError(f"{model_name} 未配置 {source} / ModelScope 下载仓库，请手动放入 models/")

        model_dir = self.root / info["subdir"]
        model_dir.mkdir(parents=True, exist_ok=True)
        for filename in info["required_files"]:
            url = self.build_file_url(source, repo, filename)
            self._download_file(url, model_dir / filename, progress=progress)
        return model_dir
```

实现 `_download_file()` 使用 `urllib.request.urlopen()` 分块写入，分块后调用 `progress(filename, downloaded, total)`；这里不直接绑定 Rich，便于测试。

- [ ] **步骤 4：补进度回调测试**

在 `tests/test_models.py` 增加：

```python
def test_download_file_reports_progress(tmp_path, monkeypatch):
    from io import BytesIO
    from subtap.core.models import ModelDownloader
    from subtap.schemas.config import SubtapConfig

    class FakeResponse:
        status = 200

        def __init__(self):
            self.fp = BytesIO(b"abc")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def getheader(self, name, default=None):
            return "3" if name.lower() == "content-length" else default

        def read(self, size=-1):
            return self.fp.read(size)

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: FakeResponse())
    downloader = ModelDownloader(SubtapConfig())
    seen = []

    downloader._download_file(
        "https://example.test/file",
        tmp_path / "file",
        progress=lambda name, done, total: seen.append((done, total)),
    )

    assert (tmp_path / "file").read_bytes() == b"abc"
    assert seen[-1] == (3, 3)
```

- [ ] **步骤 5：运行测试验证通过**

运行：

```bash
.venv/bin/python -m pytest tests/test_models.py -q
```

预期：全部通过。

- [ ] **步骤 6：Commit**

```bash
git add src/subtap/core/models.py tests/test_models.py
git commit -m "feat: 添加开发版模型下载器"
```

## 任务 3：setup 下载选择、连通性降级和参数

**文件：**
- 修改：`src/subtap/core/setup.py:47-92`
- 修改：`src/subtap/cli.py:237-285`
- 测试：`tests/test_setup.py`、`tests/test_cli.py`

- [ ] **步骤 1：编写失败测试**

在 `tests/test_setup.py` 增加：

```python
def test_setup_models_uses_selected_source(monkeypatch, tmp_path):
    from subtap.core.setup import SetupWizard

    calls = []

    class FakeDownloader:
        def __init__(self, config):
            pass

        def download(self, model_name, source="hf", progress=None):
            calls.append((model_name, source))
            return tmp_path / "models" / model_name

    monkeypatch.setattr("subtap.core.models.ModelDownloader", FakeDownloader)
    monkeypatch.setattr("subtap.core.setup.load_config", lambda path: __import__("subtap.schemas.config").schemas.config.SubtapConfig())

    ok = SetupWizard().setup_models(source="hf-mirror", include_optional=False)

    assert ok is True
    assert ("asr_0.6b", "hf-mirror") in calls
    assert ("aligner", "hf-mirror") in calls
    assert all(name != "asr_1.7b" for name, _source in calls)
```

在 `tests/test_cli.py` 增加：

```python
def test_setup_help_has_download_source_option():
    result = runner.invoke(app, ["setup", "--help"])

    assert result.exit_code == 0
    assert "--download-source" in result.output
    assert "hf-mirror" in result.output
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```bash
.venv/bin/python -m pytest tests/test_setup.py::test_setup_models_uses_selected_source tests/test_cli.py::test_setup_help_has_download_source_option -q
```

预期：失败，原因是 `source` 参数和 CLI option 未实现。

- [ ] **步骤 3：实现 setup 参数**

在 `src/subtap/cli.py` 的 `setup()` 签名改为：

```python
def setup(
    skip_models: bool = typer.Option(False, "--skip-models", help="跳过模型下载"),
    download_source: str = typer.Option(
        "ask",
        "--download-source",
        help="模型下载方式：ask / hf / hf-mirror / modelscope / manual",
    ),
    include_optional: bool = typer.Option(False, "--include-optional", help="同时下载可选大模型"),
    model_endpoint: str | None = typer.Option(None, "--model-endpoint", help="自定义 Hugging Face 镜像地址"),
) -> None:
```

删除 `--quick`、`--full`、`--mode` 的 `[待实现]` 承诺。保留 `skip_models`，新增明确参数。

- [ ] **步骤 4：实现 SetupWizard 编排**

在 `src/subtap/core/setup.py` 中：

```python
DOWNLOAD_SOURCES = ("hf", "hf-mirror", "modelscope", "manual")


class SetupWizard:
    def choose_download_source(self, requested: str = "ask") -> str:
        if requested in DOWNLOAD_SOURCES:
            return requested
        if requested != "ask":
            raise ValueError(f"未知下载方式：{requested}")

        import typer

        typer.echo("请选择模型安装方式：")
        typer.echo("  1. Hugging Face 直连")
        typer.echo("  2. Hugging Face 国内镜像（https://hf-mirror.com）")
        typer.echo("  3. ModelScope")
        typer.echo("  4. 手动放入 models/")
        choice = typer.prompt("输入序号", default="1")
        return {"1": "hf", "2": "hf-mirror", "3": "modelscope", "4": "manual"}.get(choice, "hf")

    def setup_models(self, source: str = "ask", include_optional: bool = False, endpoint: str | None = None) -> bool:
        from subtap.schemas.config import load_config
        from subtap.core.models import ModelDownloader

        config = load_config(Path.home() / ".subtap" / "config.yaml")
        if endpoint:
            config.models.hf_mirror_endpoint = endpoint
        downloader = ModelDownloader(config)
        selected = self.choose_download_source(source)
        if selected == "manual":
            self.print_manual_model_instructions()
            return False

        targets = ["asr_0.6b", "aligner"]
        if include_optional:
            targets.append("asr_1.7b")
        return all(self._download_model(downloader, name, selected) for name in targets)
```

`_download_model()` 负责 Rich 进度状态和连通性探测失败时的中文提示；交互降级在 `source == "ask"` 时进行，非交互参数模式直接返回失败。

- [ ] **步骤 5：运行测试验证通过**

运行：

```bash
.venv/bin/python -m pytest tests/test_setup.py tests/test_cli.py -q
```

预期：全部通过。

- [ ] **步骤 6：Commit**

```bash
git add src/subtap/core/setup.py src/subtap/cli.py tests/test_setup.py tests/test_cli.py
git commit -m "feat: 添加模型下载向导"
```

## 任务 4：doctor 真实失败和 CLI 模块入口

**文件：**
- 修改：`src/subtap/cli.py:67-176`
- 修改：`src/subtap/cli.py:1080-文件末尾`
- 测试：`tests/test_cli.py`

- [ ] **步骤 1：编写失败测试**

在 `tests/test_cli.py` 增加：

```python
def test_doctor_release_fails_when_models_missing(tmp_path, monkeypatch):
    from pathlib import Path

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    subtap_dir = tmp_path / ".subtap"
    subtap_dir.mkdir()
    (subtap_dir / "config.yaml").write_text("models:\n  root: models\n", encoding="utf-8")

    result = runner.invoke(app, ["doctor", "--release"])

    assert result.exit_code == 1
    assert "部分检查未通过" in result.output
    assert "缺失" in result.output


def test_python_module_entrypoint_outputs_help():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "subtap.cli", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Subtap" in result.stdout
    assert "run" in result.stdout
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```bash
.venv/bin/python -m pytest tests/test_cli.py::test_doctor_release_fails_when_models_missing tests/test_cli.py::test_python_module_entrypoint_outputs_help -q
```

预期：失败，原因是 `doctor` 模型状态不影响 `all_ok`，模块入口无输出。

- [ ] **步骤 3：修复 doctor**

在 `doctor()` 模型状态循环中：

```python
for ms in registry.status():
    icon = typer.style("✓", fg=typer.colors.GREEN) if ms.installed else typer.style("✗", fg=typer.colors.RED)
    typer.echo(f"  {icon} {ms.name}")
    if not ms.installed:
        all_ok = False
        typer.echo(f"    路径：{ms.path}")
        if ms.missing_files:
            typer.echo(f"    缺失：{', '.join(ms.missing_files)}")
```

配置无效分支也设置 `all_ok = False`。

- [ ] **步骤 4：补模块入口**

在 `src/subtap/cli.py` 文件末尾加入：

```python
if __name__ == "__main__":
    app()
```

- [ ] **步骤 5：运行测试验证通过**

运行：

```bash
.venv/bin/python -m pytest tests/test_cli.py::test_doctor_release_fails_when_models_missing tests/test_cli.py::test_python_module_entrypoint_outputs_help -q
```

预期：2 passed。

- [ ] **步骤 6：Commit**

```bash
git add src/subtap/cli.py tests/test_cli.py
git commit -m "fix: 修复 doctor 发布检查"
```

## 任务 5：文档和 release-check 对齐开发版

**文件：**
- 修改：`README.md`
- 修改：`RELEASE.md`
- 修改：`scripts/release-check.sh`
- 测试：`tests/test_release.py`

- [ ] **步骤 1：编写失败测试**

在 `tests/test_release.py` 增加：

```python
def test_readme_documents_development_model_sources():
    from pathlib import Path

    text = Path("README.md").read_text(encoding="utf-8")

    assert "macOS 开发版" in text
    assert "models/asr_0.6b" in text
    assert "https://hf-mirror.com" in text
    assert "Homebrew" not in text


def test_release_check_does_not_require_model_download():
    from pathlib import Path

    text = Path("scripts/release-check.sh").read_text(encoding="utf-8")

    assert "subtap setup --skip-models" in text
    assert "--download-source hf" not in text
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```bash
.venv/bin/python -m pytest tests/test_release.py::test_readme_documents_development_model_sources tests/test_release.py::test_release_check_does_not_require_model_download -q
```

预期：README 或 release-check 仍未对齐时失败。

- [ ] **步骤 3：更新 README**

README 必须包含：

```markdown
## 支持范围

当前版本面向 macOS 开发版源码安装，已在 Apple Silicon 环境验证。当前不提供 Homebrew、Developer ID 签名、公证或正式二进制分发。

## 模型安装

模型统一放在项目根目录 `models/`：

- `models/asr_0.6b`
- `models/asr_1.7b`（可选）
- `models/aligner`

运行 `subtap setup` 后选择模型安装方式：

1. Hugging Face 直连
2. Hugging Face 国内镜像：`https://hf-mirror.com`
3. ModelScope
4. 手动下载后放入 `models/`
```

- [ ] **步骤 4：更新 release-check**

`scripts/release-check.sh` 检查项保持开发版 smoke：

```bash
CHECKS=(
    "pip install -e ."
    "subtap setup --skip-models"
    "subtap --help"
    "subtap run --help"
    "subtap models list"
    "python -m subtap.cli --help"
)
```

- [ ] **步骤 5：运行测试验证通过**

运行：

```bash
.venv/bin/python -m pytest tests/test_release.py -q
```

预期：全部通过。

- [ ] **步骤 6：Commit**

```bash
git add README.md RELEASE.md scripts/release-check.sh tests/test_release.py
git commit -m "docs: 对齐开发版验收说明"
```

## 任务 6：全量验证和图谱更新

**文件：**
- 修改：`graphify-out/*`

- [ ] **步骤 1：运行关键测试**

运行：

```bash
.venv/bin/python -m pytest tests/test_models.py tests/test_setup.py tests/test_cli.py tests/test_release.py -q
```

预期：全部通过。

- [ ] **步骤 2：运行全量测试**

运行：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider
```

预期：全部通过。

- [ ] **步骤 3：运行开发版 CLI smoke**

运行：

```bash
HOME=/tmp/subtap-dev-acceptance .venv/bin/subtap setup --skip-models
HOME=/tmp/subtap-dev-acceptance .venv/bin/subtap --help
HOME=/tmp/subtap-dev-acceptance .venv/bin/python -m subtap.cli --help
HOME=/tmp/subtap-dev-acceptance .venv/bin/subtap doctor --release
```

预期：
- `setup --skip-models` 成功。
- 两种 help 均有输出。
- `doctor --release` 在模型缺失时退出非 0，并输出缺失模型说明。

- [ ] **步骤 4：运行静态检查观察剩余问题**

运行：

```bash
.venv/bin/ruff check src/subtap/core/models.py src/subtap/core/setup.py src/subtap/cli.py tests/test_models.py tests/test_setup.py tests/test_cli.py tests/test_release.py
```

预期：本轮触达文件无新增 ruff 错误。

- [ ] **步骤 5：更新图谱**

运行：

```bash
graphify update .
```

预期：更新成功。

- [ ] **步骤 6：Commit**

```bash
git add graphify-out
git commit -m "chore: 更新 graphify 图谱"
```

## 自检

- 覆盖验收报告硬问题：模型路径、doctor 误报、setup 假承诺、CLI 模块入口、开发版文档、release-check。
- 明确排除：Windows/Linux、Homebrew、签名公证、正式二进制、长时间稳定性压测。
- 不新增下载依赖：下载使用 stdlib，进度使用既有 `rich`。
- 避免假承诺：ModelScope 没有 repo 映射时失败并提示手动放入，不伪装自动下载成功。
- 用户选择下载方式：`setup` 默认进入联网下载向导，但不会静默下载。
