# Homebrew 锁定 Wheelhouse Formula 设计

## 状态

- **方案状态：** Rejected。许可证硬门禁未通过，禁止实现和发布。
- **已知证据：** `v0.1.0rc2` 的 GitHub prerelease、SHA256、构建来源证明和 arm64 wheel smoke 已通过。
- **已淘汰路线：** 标准 Python Formula。`brew update-python-resources` 因 `mlx` 没有源码包而失败。
- **终止证据：** 锁定 SciPy 1.18.0 arm64 wheel 捆绑 LGPL-2.1-or-later 与 GPL-3.0-or-later WITH GCC-exception-3.1 组件；项目没有书面法律审批及精确 Corresponding Source/构建材料。详见 `docs/research/2026-07-13-wheelhouse-license-review.md`。
- **载体接受条件：** 许可证审查和连续 RC A/B 的 attestation、严格审计、冷安装、升级、回滚、资料保留全部通过后，才能把分发载体 ADR 改为 Accepted。正式 tag、正式 Release、Tap 默认分支和 README 属于后续正式发布门禁。

Homebrew 官方要求 binary-only 软件进入 Cask；该要求针对 homebrew/core。本方案原计划只验证第三方 `R-jed/homebrew-tap` 是否能以 Formula 安全维护。许可证硬门禁已在实现前触发，因此下文保留为可追溯的被拒设计，不得据此继续生成 wheelhouse。

## 用户契约

- 最终命令保持 `brew install r-jed/tap/subtap`。全限定直接安装是推荐入口，只信任目标 Formula；不要求用户先手动 tap。未来 Homebrew 要求 Tap Trust 时，短名称安装不作为文档入口。
- 用户不需要安装、选择或理解 Python；Formula 使用 Homebrew `python@3.12`。
- 仅支持 Apple Silicon 和 macOS 14 Sonoma 及以上。候选构建与最低系统验收不通过时，不得继续保留 README 当前的 macOS 13.5 承诺。
- 模型不进入 Homebrew 包，首次启动后由 Subtap 模型管理器下载。
- install、upgrade、rollback、uninstall 均不得删除或修改既有 `~/.subtap` 用户资料。

## 实施前硬门禁

### 平台与依赖

- 固定 CPython 3.12、`cp312` ABI 和 `macosx_14_0_arm64` 目标。
- wheel 是否可用由 Python 3.12/macOS 14/arm64 的 `packaging.tags` 兼容集合判定：接受 `py3-none-any`，以及最低部署版本不高于 14 且包含 arm64 slice 的 arm64/universal2 wheel；拒绝最低系统高于 14、x86-only、其他 OS 或不兼容 ABI。禁止用文件名字符串白名单代替兼容性判定。
- 当前锁定闭包约 64 个包，第三方压缩包约 277 MB，venv 安装后约 1 GB。每次候选分别记录 Subtap/wheelhouse、Formula dependencies 和包含 Homebrew Python/FFmpeg 后的用户实际安装增量；wheelhouse 超过 350 MB 或 venv 超过 1.3 GB 即停止 Formula 路线并比较 Cask。
- `jieba==0.42.1` 只有锁定 sdist。允许 RC workflow 在无网络、隔离的 PEP 517 环境中从该纯 Python sdist 构建 wheel；输入 sdist、build-system 依赖 wheel 和输出 wheel 都必须锁定并校验 SHA256，全部纳入来源证明。build isolation 不得联网补装。任何其他 sdist 或任何 native sdist 立即终止。

### 许可证

- 扫描每个 wheel 的 `METADATA`、`License-File`、`.dist-info/licenses` 和 bundled component notices，不能只读取顶层 classifier。
- 允许 MIT、BSD、Apache-2.0、ISC、PSF 等项目明确批准的宽松许可证。
- AGPL、GPL、LGPL、未知许可证和未识别表达式默认拒绝。带 GCC Runtime Library Exception 的组件也必须出现在报告中，只有书面许可证审查明确批准后才能放行。
- 当前 SciPy wheel 已发现 LGPL 组件和 `GPL-3.0-with-GCC-runtime-exception` 组件；在许可证审查结论记录前，本路线保持阻塞。切换 Cask不会消除再分发义务。

## Wheelhouse 产物

连续两个 RC 候选 A/B 都在真实 arm64 macOS runner 上生成：

```text
subtap-X-macos14-arm64-wheelhouse.tar.gz
├── requirements.txt
├── manifest.json
├── licenses.json
├── THIRD_PARTY_LICENSES/
└── wheels/
    ├── subtap-X-py3-none-any.whl
    └── 完整运行依赖闭包
```

### 生成不变量

- workflow 开头断言 `uname -m=arm64` 和 macOS 版本，记录 `brew config`、Python、Homebrew、MLX 和 SDK 版本。
- tag `vX`、`pyproject.toml`、wheel METADATA、Subtap wheel 文件名、wheelhouse 文件名和 Formula `version X` 必须完全一致。
- Release target commit 必须等于 tag peeled commit。
- 从 `uv.lock` 为 Python 3.12/macOS 14 arm64 选择唯一文件，下载字节必须匹配锁文件 SHA256。
- `requirements.txt` 稳定排序，每项固定 `name==version` 和 SHA256；pip 通过 `--find-links` 指向归档内 wheels 目录，并强制 `--no-index --require-hashes --only-binary=:all:`。
- `manifest.json` 记录每个 wheel 的名称、版本、SHA256、大小、wheel tags、原始 URL 和来源包。
- `licenses.json` 记录顶层许可证、内置组件许可证、扫描结论和审批依据。
- Subtap wheel 可包含 `subtap/resources/model_manifest.yaml`，但不得包含模型权重、真实用户数据或生成期下载文件。模型排除按路径、扩展名和归档清单验证，不按字符串 `models` 粗略判断。

### 构建后验证

在全新 venv 中执行：

```bash
python -m pip install --no-index --find-links "$PWD/wheels" --require-hashes --only-binary=:all: -r requirements.txt
python -m pip check
python -c "import mlx, mlx_audio, onnxruntime, torch, torchaudio, scipy, numpy"
subtap version
subtap doctor --json
```

实际安装的运行闭包 name/version 必须与 `manifest.json` 完全一致；venv 自带的 pip bootstrap 不计入运行闭包比较。Doctor 只允许明确的模型缺失；`models_error` 或其他检查错误立即失败。

Wheelhouse tar、`SHA256SUMS`、`manifest.json` 和 `licenses.json` 都必须成为 provenance subject。Formula 生成前执行 `gh attestation verify` 并再次核对 GitHub Release asset digest；同一 tag 已存在同名不同 digest 资产时拒绝覆盖。

## Formula 契约

Tap 默认分支最终只保留 `Formula/subtap.rb`。Formula 必须显式包含：

- `version X`、`license "MIT"`、整个 wheelhouse 的固定 HTTPS URL 和 SHA256。
- `depends_on arch: :arm64`、`depends_on macos: :sonoma`。
- `depends_on "python@3.12"` 和 `depends_on "ffmpeg"`。
- 在 `libexec` 创建 venv，仅以 `--no-index --find-links #{buildpath/"wheels"} --require-hashes --only-binary=:all:` 安装归档内容。
- 将 `libexec/bin/subtap` 链接到 Formula `bin`。
- install/post_install 不访问 PyPI、GitHub API、模型源或用户 Python，不修改动态库搜索路径。

`test do` 使用 Homebrew 自动提供的 testpath/HOME，必须验证：

1. `subtap version` 等于 Formula 版本。
2. `subtap doctor --json` 是合法 JSON。
3. 未安装模型时只有明确 missing-model 状态；`models_error` 或其他错误失败。
4. 原生依赖 import 成功。
5. 不下载模型、不读取真实 `~/.subtap`。

## 候选、升级与回滚

首次发布不能凭单个版本宣称升级/回滚通过，必须连续生成候选 A/B：

1. 候选 A 完成冷安装与 Formula test。
2. 在隔离 Tap 候选分支的 commit A 安装 A。
3. 切换到 commit B，执行 `brew upgrade`，断言版本从 `EXPECTED_PREVIOUS_VERSION` 精确变为 `EXPECTED_CANDIDATE_VERSION`。
4. 切回 commit A 并 reinstall，断言版本精确恢复为 A。
5. 只有 B 可以成为正式 Formula 的基础。

验收 runner 禁用 Homebrew auto-update/cleanup，前置确认没有已安装 Subtap，并记录 Tap commit。缺少 A、版本未变化或回滚不一致都属于阻塞，不能当作“已是最新版”。

## 后续正式发布门禁：正式资产与 Tap 原子更新

本节不在当前载体验证阶段自动执行，必须在载体 ADR Accepted 后获得正式发布授权。RC wheelhouse 只验证载体，不直接进入 Tap 默认分支。正式流程分两阶段：

1. 在 Tap candidate branch 或固定本地 Tap commit 验证 Formula，不预先污染默认分支。
2. 生成正式 `0.1.0` wheelhouse并把 Formula URL 替换为正式 GitHub Release后，重新执行 attestation、digest、audit、冷安装和 Formula test。
3. 记录开始验证时的 Tap 默认分支 SHA；仅当远端 HEAD 仍等于该 SHA时，以单个 Formula commit fast-forward 更新。HEAD 已变化则停止并重新验证。
4. 任何失败都保留旧 Formula；不推送半成品，不覆盖旧版本资产。

## 完整验收

在一次性 Apple Silicon GitHub runner 上执行：

1. `brew audit --strict --online r-jed/tap/subtap`。
2. `brew install --build-from-source r-jed/tap/subtap`。
3. `brew test r-jed/tap/subtap`。
4. version、Doctor、TUI help 和原生依赖 smoke。
5. 候选 A→B 升级、B→A 回滚。
6. 正式 Formula 再次冷安装。
7. 卸载并验证用户资料。

用户资料验收在开始前为 `config.yaml`、`batch-config.yaml`、`state.json`、`profile/`、`history/`、`models/`、`glossaries/`、`manuscripts/`、`jobs/` 写入不同哨兵并记录 SHA256；升级后、回滚后、正式安装后和卸载后逐项复核。cache/logs 不要求内容不变，但不得删除整个 `~/.subtap` 或越界删除。

临时目录清理前必须 `realpath` 确认位于本次带 marker 的允许根目录。失败时先保存证据，再清理。

## 日志与机器门禁

workflow 以 `if: always()` 上传：

- Formula snapshot、Tap base/candidate commit、Release URL和 digest。
- attestation verify、brew config/audit/test/install/upgrade/rollback/uninstall 完整输出和退出码。
- wheelhouse manifest、licenses、体积、pip check、原生 import 和 Doctor JSON。
- 用户资料哨兵在每个阶段的校验结果。

后续正式发布中，README 公开安装命令必须同时满足：

- ADR 状态为 Accepted 并包含成功 run URL。
- Tap 默认分支 Formula SHA 等于已验证正式候选。
- 正式 Release Formula 重验成功。
- 发布清单全部确认。

CI 对 README 执行机器检查；任一条件不满足时，出现可见的 `brew install r-jed/tap/subtap` 代码块即失败。

## 失败与终止条件

以下任一情况立即停止 Formula 路线并把证据写入 ADR：

- 许可证硬门禁不能通过。
- 任一 native 依赖没有兼容 wheel，或只能在 Homebrew install期构建。
- Python/MLX 原生库无法在隔离环境加载。
- 严格审计、真实安装、Formula test、升级、回滚或卸载不可重复通过。
- Formula 必须联网补装、修改动态库路径或依赖用户 Python。
- 超过体积门禁。

终止后进入 Cask 自包含运行时设计，不在 Formula 中增加下载器、兼容补丁或静默降级。

## 参考

- [Homebrew Python Formula 指南](https://docs.brew.sh/Python-for-Formula-Authors)
- [Homebrew Formula Cookbook](https://docs.brew.sh/Formula-Cookbook)
- [创建与维护 Tap](https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap)
- [Acceptable Formulae](https://docs.brew.sh/Acceptable-Formulae)
- [Formula 版本](https://docs.brew.sh/Versions)
- [Tap Trust](https://docs.brew.sh/Tap-Trust)

## 非目标

- 不进入 homebrew/core。
- 不发布 Intel、Linux 或 Windows 包。
- 不把模型放进 wheelhouse。
- 不在本阶段发布 PyPI 正式版或创建正式 tag。
- 不保留 Formula、Cask 和 launcher 三套并行实现。
