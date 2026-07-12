# 阶段 1：Apple Silicon Homebrew 分发验证实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在不下载模型、不要求用户理解 Python 的前提下，完成三种 Homebrew 载体的真实冷安装验证，依据固定门禁选出唯一载体，并把 Apple Silicon 发布链路变成可重复、可审计、可回滚的流程。

**架构：** 阶段 1 只解决程序分发，不改字幕 pipeline、模型管理和 TUI。三个原型共享同一份验收脚本和评分规则：Formula 使用 Homebrew 隔离 Python 环境，Cask 安装自包含 arm64 产物，轻量 Formula 安装启动器并由启动器创建锁定运行时；原型只能在一次性 HOME 和独立 Tap 中运行。选择结果写入 ADR，未获选原型全部删除，正式发布流程只保留一个载体。

**技术栈：** Homebrew Formula/Cask、Ruby、uv、GitHub Actions、PyPI/GitHub Release、SHA256、GitHub artifact attestations、pytest、Bash。

---

## 完成标准

- 阶段 0 审查发现的 3 个问题全部关闭：Doctor 异常失败退出、`check.sh` 自己同步锁定依赖、第三方 Actions 固定完整 SHA。
- Formula、Cask、轻量启动器均在 Apple Silicon Mac 的一次性 HOME 中执行安装、`subtap version`、`subtap doctor --json`、升级、卸载与数据保留检查。
- 每个失败原型保留完整原因，禁止用跳过审计、联网补装未锁定依赖或修改用户 Python 环境换取通过。
- ADR 按固定优先级选出唯一载体：冷安装可重复 > 用户无需理解 Python > 可回滚 > `brew audit` 通过 > 体积。
- 正式 workflow 只在前置测试、构建、哈希、来源证明和 Homebrew 验证全部通过后更新 Tap；失败时旧版本保持可安装。
- 不触碰 ASR、对齐、断句、模型下载和 TUI 行为。

## 文件结构

- 修改：`src/subtap/cli/doctor_cli.py` — 模型状态无法检查时令 release Doctor 失败。
- 修改：`tests/test_doctor_release.py` — 锁定模型检查异常的 Fail Fast 行为。
- 修改：`scripts/check.sh` — 由唯一入口按 `uv.lock` 同步开发依赖。
- 修改：`.github/workflows/ci.yml` — 删除重复安装并固定 Actions SHA。
- 修改：`.github/workflows/release.yml` — 固定 Actions SHA、最小权限、构建校验与来源证明。
- 创建：`packaging/homebrew/acceptance.sh` — 三种载体共用的冷安装、升级、卸载验收器。
- 创建：`packaging/homebrew/fixtures/Formula/subtap.rb` — Formula 隔离 Python 原型。
- 创建：`packaging/homebrew/fixtures/Casks/subtap.rb` — 自包含 arm64 Cask 原型。
- 创建：`packaging/homebrew/fixtures/Formula/subtap-launcher.rb` — 轻量启动器 Formula 原型。
- 创建：`packaging/homebrew/launcher/subtap` — 锁定运行时启动器原型。
- 创建：`packaging/homebrew/evaluate.py` — 读取三份验收 JSON，按固定规则产生唯一选择。
- 创建：`tests/test_homebrew_evaluate.py` — 选择规则回归测试。
- 创建：`docs/adr/0001-homebrew-distribution-carrier.md` — 记录证据、选择与被拒方案。
- 修改：`README.md` — 只在正式冷安装验证通过后开放 Homebrew 命令。

## 约束与复用决策

- Formula 依照 Homebrew 官方 Python 应用规范使用 `libexec` 虚拟环境和完整 `resource`，不在安装时临时解析依赖。
- Cask 只接收 GitHub Release 中带 SHA256 的 arm64 自包含产物；不把模型放入产物。
- 轻量启动器只允许安装 `uv.lock` 对应的固定版本与哈希，不允许 `pip install subtap` 或下载 `latest`。
- 不引入新的打包框架。自包含原型先用现有 `uv` 环境生成可搬移归档；若 MLX/原生库证明不可搬移，该原型如实失败，不追加 PyInstaller/Nuitka 兼容层。
- 三个原型均只面向 Apple Silicon macOS；Intel、Linux、Windows 明确失败。

### 任务 0：关闭阶段 0 审查问题

**文件：**
- 修改：`src/subtap/cli/doctor_cli.py:357`
- 修改：`tests/test_doctor_release.py`
- 修改：`scripts/check.sh`
- 修改：`.github/workflows/ci.yml`
- 修改：`.github/workflows/release.yml`

- [ ] **步骤 1：编写 Doctor 异常失败测试**

```python
def test_release_doctor_fails_when_model_status_cannot_be_checked(monkeypatch):
    monkeypatch.setattr(
        "subtap.cli.doctor_cli.ModelRegistry.status",
        lambda _self: (_ for _ in ()).throw(RuntimeError("registry unavailable")),
    )
    result = runner.invoke(app, ["doctor", "--release", "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["models_error"] == "registry unavailable"
```

- [ ] **步骤 2：确认测试先失败**

运行：`uv run pytest -q tests/test_doctor_release.py::test_release_doctor_fails_when_model_status_cannot_be_checked`

预期：FAIL；当前 JSON 中 `ok` 仍为 `true` 或退出码为 0。

- [ ] **步骤 3：令模型检查异常影响 release 结果**

在 `except Exception as e:` 中保留 `models_error`，并增加：

```python
if release:
    all_ok = False
```

- [ ] **步骤 4：让唯一检查入口同步锁定依赖**

在 `scripts/check.sh` 进入仓库根目录后增加：

```bash
echo "==> sync locked development environment"
uv sync --frozen --extra dev --extra ai
```

从 CI 与 release test job 删除 `pip install -e ".[dev,ai]"`。保留 `setup-uv`，使本地和 CI 都由同一脚本决定依赖状态。

- [ ] **步骤 5：固定 Actions 完整 SHA**

用各 Action 官方仓库对应发布标签的 commit SHA 替换本计划触及的 `@vN`。运行 `git ls-remote https://github.com/astral-sh/setup-uv.git refs/tags/v4` 以及其他 Action 的官方仓库标签查询；只接受命令返回的 40 位 SHA，版本标签保留为行尾注释，例如 `# v4`。不得复制博客或第三方清单中的 SHA。

- [ ] **步骤 6：验证阶段 0 门禁闭合**

运行：`./scripts/check.sh`

预期：Black、mypy、pytest、build、release packaging 全部通过；日志首先显示锁定环境同步。

运行：`git grep -nE 'uses: [^ ]+@v[0-9]+' -- .github/workflows`

预期：无输出。

- [ ] **步骤 7：Commit**

```bash
git add src/subtap/cli/doctor_cli.py tests/test_doctor_release.py scripts/check.sh .github/workflows/ci.yml .github/workflows/release.yml
git commit -m "fix: 关闭阶段零发布门禁缺口" -m "问题或需求描述：Doctor 会吞掉模型检查异常，统一检查入口未自行同步依赖，Actions 未固定来源。" -m "修复或实现思路：release 检查失败退出，由 check.sh 按锁文件同步环境，并将 Actions 固定到官方 commit SHA。"
```

### 任务 1：建立三种载体共用的冷安装验收器

**文件：**
- 创建：`packaging/homebrew/acceptance.sh`

- [ ] **步骤 1：写出只接受一次性目录的安全入口**

脚本必须接收 `carrier`、`formula_or_cask`、`artifact`、`result_json` 四个参数，并在任何 Homebrew 命令前验证：

```bash
[[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]]
[[ "$TEST_HOME" == /tmp/subtap-homebrew-* ]]
[[ "$HOMEBREW_CACHE" == "$TEST_HOME"/* ]]
[[ "$result_json" == "$TEST_HOME"/* ]]
```

不满足任一条件立即退出 2；脚本不得删除参数以外路径。

- [ ] **步骤 2：实现一致的验收序列**

每个载体按顺序执行并记录耗时、磁盘占用和退出码：

```bash
brew audit --strict "$formula_or_cask"
brew install "$formula_or_cask"
subtap version
subtap doctor --json
brew reinstall "$formula_or_cask"
brew uninstall "$formula_or_cask"
test -d "$TEST_HOME/.subtap"
```

验收 HOME 中预先创建 `$TEST_HOME/.subtap/glossary/user.txt`，卸载后内容必须仍为 `保留我`。任何命令失败都令整体失败，但仍通过 `trap` 写出 JSON 结果和日志路径。

- [ ] **步骤 3：验证安全拒绝行为**

运行：`TEST_HOME="$HOME" packaging/homebrew/acceptance.sh formula subtap /tmp/a /tmp/result.json`

预期：退出 2；未执行 `brew install`，未改动真实 `~/.subtap`。

- [ ] **步骤 4：Commit**

```bash
git add packaging/homebrew/acceptance.sh
git commit -m "test: 建立 Homebrew 冷安装验收器" -m "问题或需求描述：三种分发载体缺少相同且安全的比较基准。" -m "修复或实现思路：在一次性 HOME 中统一验证审计、安装、升级、卸载和用户数据保留。"
```

### 任务 2：验证 Formula 隔离 Python 原型

**文件：**
- 创建：`packaging/homebrew/fixtures/Formula/subtap.rb`

- [ ] **步骤 1：生成完整 Python 资源清单**

运行：

```bash
brew create --python "$(pwd)/dist/subtap-0.1.0.tar.gz" --set-name subtap
brew update-python-resources --print-only subtap > /tmp/subtap-python-resources.rb
```

将生成的每个资源 URL 与 SHA256 写入 fixture。若 `mlx`、`mlx-audio` 或 `onnxruntime` 只能以 arm64 wheel 安装，资源仍必须固定 URL 和 SHA256；不得在 `install` 中联网解析。

- [ ] **步骤 2：实现最小 Formula**

Formula 必须包含 `depends_on arch: :arm64`、固定 `python@3.12`、`ffmpeg`，在 `libexec` 中创建虚拟环境，并只从已声明资源安装。`test do` 只运行：

```ruby
assert_match version.to_s, shell_output("#{bin}/subtap version")
assert_match '"ok"', shell_output("#{bin}/subtap doctor --json", 1)
```

Doctor 可因模型未下载返回 1，但必须正常启动并输出 JSON。

- [ ] **步骤 3：执行真实冷安装验收**

运行：

```bash
TEST_HOME="$(mktemp -d /tmp/subtap-homebrew-formula.XXXXXX)"
TEST_HOME="$TEST_HOME" packaging/homebrew/acceptance.sh formula \
  packaging/homebrew/fixtures/Formula/subtap.rb \
  dist/subtap-0.1.0.tar.gz \
  "$TEST_HOME/formula.json"
```

预期：产生 `formula.json`。任何原生依赖构建、审计或运行失败均保留真实失败，不添加安装后补丁。

- [ ] **步骤 4：Commit**

```bash
git add packaging/homebrew/fixtures/Formula/subtap.rb
git commit -m "test: 验证 Formula 隔离运行时" -m "问题或需求描述：需要确认 MLX Python 依赖能否遵守 Homebrew Formula 规则。" -m "修复或实现思路：固定全部资源并执行 Apple Silicon 冷安装验收。"
```

### 任务 3：验证 Cask 自包含 arm64 原型

**文件：**
- 创建：`packaging/homebrew/fixtures/Casks/subtap.rb`
- 创建：`packaging/homebrew/build-cask-artifact.sh`

- [ ] **步骤 1：构建不含模型的自包含归档**

`build-cask-artifact.sh` 从 `pyproject.toml` 读取 `VERSION`，使用 `uv sync --frozen` 建立运行时，将应用与其锁定依赖复制到 staging，删除缓存、测试和 `models/`，再生成 `subtap-${VERSION}-macos-arm64.tar.gz` 与 `.sha256`。脚本必须在归档后执行：

```bash
env -i HOME="$TEST_HOME" PATH="/usr/bin:/bin" \
  "$STAGING/bin/subtap" version
```

如果搬移后的原生库无法加载，原型失败并保留日志；禁止修改 `DYLD_LIBRARY_PATH` 指向开发机目录。

- [ ] **步骤 2：实现 Cask fixture**

Cask 固定 `arch arm: "arm64"`、本地产物 URL 和 SHA256，使用 `binary "subtap/bin/subtap"` 暴露命令。`uninstall` 只移除程序，不声明 `zap`，确保 `~/.subtap` 不被删除。

- [ ] **步骤 3：执行真实冷安装验收**

运行：

```bash
packaging/homebrew/build-cask-artifact.sh
TEST_HOME="$(mktemp -d /tmp/subtap-homebrew-cask.XXXXXX)"
TEST_HOME="$TEST_HOME" packaging/homebrew/acceptance.sh cask \
  packaging/homebrew/fixtures/Casks/subtap.rb \
  dist/subtap-0.1.0-macos-arm64.tar.gz \
  "$TEST_HOME/cask.json"
```

预期：产生 `cask.json`；归档中不存在 `models/`，卸载后测试热词仍存在。

- [ ] **步骤 4：Commit**

```bash
git add packaging/homebrew/build-cask-artifact.sh packaging/homebrew/fixtures/Casks/subtap.rb
git commit -m "test: 验证 Cask 自包含运行时" -m "问题或需求描述：需要确认 arm64 原生依赖能否随程序可靠搬移。" -m "修复或实现思路：构建不含模型的固定归档并执行隔离冷安装验收。"
```

### 任务 4：验证轻量启动器原型

**文件：**
- 创建：`packaging/homebrew/launcher/subtap`
- 创建：`packaging/homebrew/fixtures/Formula/subtap-launcher.rb`

- [ ] **步骤 1：实现版本锁定、可回滚的启动器**

启动器从随 Formula 安装的版本清单读取 `VERSION`，只使用 `~/.subtap/runtime/$VERSION`，以 `mkdir` 锁避免并发初始化。首次运行通过 Homebrew 依赖 `uv` 执行：

```bash
uv venv --python 3.12 "$runtime_tmp"
uv pip install --python "$runtime_tmp/bin/python" \
  --require-hashes -r "$formula_prefix/share/subtap/runtime-requirements.txt"
"$runtime_tmp/bin/subtap" version
mv "$runtime_tmp" "$runtime_final"
```

所有 URL、版本和 SHA256 来自发布时生成的 `runtime-requirements.txt`；成功前不得替换旧 runtime。失败时保留错误日志并删除本次 `.partial`，不得回退为系统 Python。

- [ ] **步骤 2：实现最小启动器 Formula**

Formula 依赖 `uv` 和 `ffmpeg`，安装启动器及固定 requirements。`test do` 只验证启动器的 `--bootstrap-info`，禁止 Homebrew test 隐式下载运行时。

- [ ] **步骤 3：执行在线首次运行和离线复用验收**

第一次运行允许从固定 URL 下载；第二次清空网络代理并执行 `subtap version`，必须直接复用现有 runtime。随后安装较旧 fixture，验证旧 runtime 仍可启动，最后卸载并确认两个 runtime 和热词均保留。

- [ ] **步骤 4：Commit**

```bash
git add packaging/homebrew/launcher/subtap packaging/homebrew/fixtures/Formula/subtap-launcher.rb
git commit -m "test: 验证锁定运行时启动器" -m "问题或需求描述：需要评估最小 Homebrew 包与首次初始化运行时的可用性。" -m "修复或实现思路：使用固定哈希、原子安装和版本目录验证首次运行及回滚。"
```

### 任务 5：以固定规则选择唯一载体并删除失败原型

**文件：**
- 创建：`packaging/homebrew/evaluate.py`
- 创建：`tests/test_homebrew_evaluate.py`
- 创建：`docs/adr/0001-homebrew-distribution-carrier.md`
- 删除：未获选的两个 fixture 与其专用脚本

- [ ] **步骤 1：编写选择规则测试**

```python
def result(name, *, cold=True, hidden=True, rollback=True, audit=True, size=100):
    return {
        "carrier": name,
        "cold_install": cold,
        "python_hidden": hidden,
        "rollback": rollback,
        "audit": audit,
        "installed_bytes": size,
    }


def test_rejects_carrier_that_fails_a_mandatory_gate():
    assert select([result("formula", audit=False), result("cask")]) == "cask"


def test_prefers_no_python_knowledge_before_smaller_size():
    assert select([result("formula", hidden=False, size=10), result("cask", size=100)]) == "cask"


def test_prefers_rollback_before_smaller_size():
    assert select([result("formula", rollback=False, size=10), result("cask", size=100)]) == "cask"


def test_returns_no_selection_when_all_carriers_fail():
    assert select([result("formula", cold=False), result("cask", audit=False)]) is None
```

评分不是可调权重。五个字段按顺序比较：`cold_install`、`python_hidden`、`rollback`、`audit` 必须全部为 true；仅在全部硬门禁通过后按 `installed_bytes` 选择更小者。并列时优先 Formula、其次 Cask、最后 launcher，以减少自管理运行时。

- [ ] **步骤 2：确认测试先失败**

运行：`uv run pytest -q tests/test_homebrew_evaluate.py`

预期：FAIL；`packaging.homebrew.evaluate` 尚不存在。

- [ ] **步骤 3：实现最小评估器**

评估器读取三个 JSON，输出：

```json
{"selected":"formula","qualified":["formula"],"rejected":{"cask":["audit"],"launcher":["rollback"]}}
```

没有合格项时退出 1，禁止默认为现有 Formula。

- [ ] **步骤 4：生成并人工核对 ADR**

ADR 必须列出每个原型的命令、产物大小、耗时、门禁结果、失败日志路径和最终选择。结论只能来自评估器输出。删除两个失败原型后再次运行获选载体验收，确认删除没有破坏共享脚本。

- [ ] **步骤 5：Commit**

```bash
git add packaging/homebrew tests/test_homebrew_evaluate.py docs/adr/0001-homebrew-distribution-carrier.md
git commit -m "docs: 确定 Homebrew 分发载体" -m "问题或需求描述：Formula、Cask 与启动器需要以相同证据选择，不能凭偏好定案。" -m "修复或实现思路：按硬门禁和体积规则自动评估，记录被拒原因并只保留唯一方案。"
```

### 任务 6：固化发布完整性与 Tap 更新门禁

**文件：**
- 修改：`.github/workflows/release.yml`
- 修改：`.github/workflows/ci.yml`
- 修改：`README.md`

- [ ] **步骤 1：拆分最小权限**

workflow 顶层设为：

```yaml
permissions:
  contents: read
```

仅 `github-release` 增加 `contents: write` 与 `id-token: write`，仅 PyPI publish 保留 `id-token: write`。Tap 更新使用专用环境 secret，且 job 只在前述发布 job 和 Homebrew 验收 job 成功后运行。

- [ ] **步骤 2：生成哈希和构建来源证明**

构建 job 为所有正式产物生成 `SHA256SUMS`；使用 GitHub 官方 attestation Action 为产物目录生成来源证明。所有 Actions 均固定官方完整 SHA并保留版本注释。

- [ ] **步骤 3：让 Tap 更新成为最后一步**

先在临时 clone 中写入新版本与 SHA256，运行：

```bash
brew audit --strict r-jed/tap/subtap
brew install r-jed/tap/subtap
brew test r-jed/tap/subtap
```

三项全部通过后才 commit/push Tap。失败时不得改远端 Tap，GitHub Release 与 PyPI 可保持已发布状态，但 workflow 明确失败并给出重新运行 Tap job 的路径。

- [ ] **步骤 4：开放 README 安装命令**

仅当真实 Tap 冷安装通过后，将开发状态替换为：

```bash
brew install r-jed/tap/subtap
subtap
```

README 同时写明：程序卸载不会删除 `~/.subtap` 中的模型、热词、文稿和历史任务。

- [ ] **步骤 5：验证完整阶段 1**

运行：`./scripts/check.sh`

预期：全部通过。

运行：`CARRIER_PATH="$(python packaging/homebrew/evaluate.py --print-selected-path /tmp/subtap-homebrew-results/*.json)" && brew audit --strict "$CARRIER_PATH" && brew install "$CARRIER_PATH" && brew test subtap`

预期：全部通过；`subtap doctor --json` 能启动且模型缺失被准确报告。

运行：`git diff --check && git grep -nE 'uses: [^ ]+@v[0-9]+' -- .github/workflows`

预期：两条命令均无输出。

运行：`test -s "/Users/qunqing/Downloads/ASR-SRT测试音频/subtap-1.7b-review-final-20260712/output/高质量中文语音.srt"`

预期：文件存在且非空；阶段 1 未改字幕 pipeline，因此不重复消耗模型运行时间。

- [ ] **步骤 6：更新代码图并 Commit**

运行：`graphify update .`

```bash
git add .github/workflows/ci.yml .github/workflows/release.yml README.md graphify-out
git commit -m "ci: 固化 Apple Silicon Homebrew 发布门禁" -m "问题或需求描述：发布产物、来源证明和 Tap 更新缺少不可绕过的顺序约束。" -m "修复或实现思路：最小化权限，校验产物与来源，Homebrew 验收成功后才更新 Tap。"
```

## 计划自检

- 规格覆盖：阶段 1 的三原型、固定选择、Apple Silicon、校验、Tap 更新、Actions SHA、最小权限、来源证明和回滚均有对应任务。
- 范围边界：没有修改字幕 pipeline、模型下载、资源目录或 TUI；模型仍不进入安装包。
- Fail Fast：任一原型或发布门禁失败都会停止，不存在默认选中或静默降级。
- 安全边界：所有安装测试使用 `/tmp/subtap-homebrew-*` HOME；卸载不删除用户资料。
- 复用：仅使用 Homebrew、uv 与 GitHub 官方发布能力，没有自建包管理器或更新系统。
- 人工门禁：README 的 Homebrew 命令只有真实 Tap 冷安装通过后才允许公开。
