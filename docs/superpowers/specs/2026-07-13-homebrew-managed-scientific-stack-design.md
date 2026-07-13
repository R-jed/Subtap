# Homebrew 托管科学计算栈 Formula 设计

## 状态与目标

- **状态：** Proposed。已确认锁定的 SentencePiece 0.2.1 wheel 没有与当前文件匹配的 provenance；新候选改用官方 SentencePiece 0.2.2 CPython 3.13 arm64 wheel。该文件的 GitHub Release、PyPI 和 SLSA subject SHA256 完全一致，等待许可证闭包与运行原型验证。
- **目标：** 保持 `brew install r-jed/tap/subtap` 的一条命令体验，同时让 Homebrew 官方 Formula 管理 NumPy、SciPy、GCC 和 OpenBLAS，Subtap Release 不再复制或托管 SciPy/GCC 二进制。
- **前置结论：** 标准 Python Formula 因 MLX 无 sdist 被淘汰；锁定完整 wheelhouse 因 SciPy wheel 的 LGPL/GPL Runtime Exception 组件被淘汰。

本设计只验证公开第三方 Tap，不申请进入 homebrew/core。Formula、Tap 和 README 在真实验收前保持未发布状态。

## 产品边界

- 只支持 Apple Silicon 和 macOS 14 Sonoma 及以上。
- Formula 固定使用 Homebrew `python@3.13`；用户不管理 Python。
- Homebrew 官方 `numpy`、`scipy`、`gcc`、`openblas` 作为独立 Formula 依赖，由 Homebrew 获取、安装和维护。
- Subtap wheelhouse 明确排除 NumPy、SciPy、GCC/OpenBLAS 及其动态库。
- SentencePiece 只允许使用下文固定的官方 `0.2.2` wheel、SLSA provenance 和许可证闭包；不自建 wrapper，不依赖滚动的 Homebrew SentencePiece runtime，也不接受其他版本或 hash。
- 模型不进入程序包，继续由 Subtap 模型管理器下载。
- install、upgrade、rollback、uninstall 不得删除或修改 `~/.subtap` 既有资料。

## 已验证的兼容前提

- 项目声明 Python `>=3.10`，没有排除 Python 3.13。
- 锁文件已包含 MLX、MLX-Metal、ONNX Runtime、Torch 和 TorchAudio 的 Python 3.13/macOS arm64 wheels。
- MLX-Audio 0.4.3 要求 `numpy>=1.26.4`、`scipy>=1.10.0`。
- Homebrew 官方 NumPy、SciPy 当前提供 Sonoma arm64 bottle，并安装到 Python 3.13 和 3.14。
- MLX-Audio 0.4.3 声明 `sentencepiece>=0.2.0`，因此 `0.2.2` 位于上游公开兼容范围内；实现前必须把 `uv.lock` 从 0.2.1 升级到 0.2.2，锁文件和 wheelhouse manifest 必须共同固定下述 hash。
- 官方 CPython 3.13/macOS arm64 wheel 名为 `sentencepiece-0.2.2-cp313-cp313-macosx_11_0_arm64.whl`，SHA256 为 `201a8e0f55501a76e08dbf2c54bc45f4642b379271e89c667d517bfbc2191f2a`。GitHub Release asset 与 PyPI 文件的名称、大小和 SHA256 相同。
- 官方 SLSA provenance bundle SHA256 为 `cc6f6011e50a3ed6099e0cdfe59ae517c16d2b40c74de76eebaa8e8426f0486b`；已用固定 `slsa-verifier` 验证通过。subject 精确绑定上述文件和 SHA256，config source 为 tag `v0.2.2`、commit `e0cce7d37b065b5140349dbe12c6bcf6192fdd78`、workflow `.github/workflows/wheel.yml`。
- 该 wheel 的 `License-Expression` 为 Apache-2.0，`otool -L` 只显示 macOS `libc++` 与 `libSystem`，没有外部 SentencePiece、GCC 或 OpenBLAS 动态库；但 wheel 内没有许可证文件，因此仍需补齐下文规定的随附通知。
- GitHub 把 `v0.2.2` Release 标记为 prerelease，PyPI 版本和 Homebrew Formula 则按稳定 `0.2.2` 发布。本设计只把它作为 RC 候选；该状态差异必须记录在验收证据中，不能隐藏。

这些只是进入原型的前提，不是运行成功证据。任何一项在实现时发生变化，都必须重新检查。

## Formula 架构

候选 Formula 显式声明：

```ruby
depends_on arch: :arm64
depends_on macos: :sonoma
depends_on "python@3.13"
depends_on "numpy"
depends_on "scipy"
depends_on "ffmpeg"
```

安装流程：

1. 使用 Homebrew `python@3.13` 在 `libexec` 创建普通 venv，不启用 `--system-site-packages`。
2. 在 venv site-packages 写入专用 `.pth`，只加入 `Formula["numpy"].opt_lib/"python3.13/site-packages"` 和 `Formula["scipy"].opt_lib/"python3.13/site-packages"` 两个稳定 `opt` symlink 字面路径；写入前禁止把它们 `realpath` 成带版本号的 Cellar keg 路径。
3. 验证时再解析 `numpy.__file__`、`scipy.__file__` 和各自 `opt_prefix` 的 realpath，确认导入文件位于当前 Cellar keg，且 venv 本地没有同名包。
4. 从当前 Release 的锁定 wheelhouse 安装剩余运行闭包，使用 `--no-index --find-links wheels --no-deps --require-hashes --only-binary=:all:`。
5. 把 `licenses.json` 和 `THIRD_PARTY_LICENSES/` 安装到 `pkgshare/third-party-licenses`，确保源码安装和未来 bottle 都保留通知；Formula test 逐项校验文件与 SHA256。
6. 链接 `libexec/bin/subtap` 到 Formula `bin`。
7. 执行 `pip check`，确认 MLX-Audio 的 NumPy/SciPy 依赖由 Homebrew 包满足。

Subtap Formula 自身不会访问 PyPI。Homebrew 仍会从官方 bottle 源下载其声明依赖；文档不得把整个 `brew install` 描述为离线安装。

## 精确依赖边界

wheelhouse 生成器从 Python 3.13/macOS 14/arm64 的锁定运行闭包中排除：

- `numpy`
- `scipy`
- 仅由 Homebrew NumPy/SciPy Formula 管理的 GCC/OpenBLAS 组件

其余包必须满足：

- wheel tag 与 Python 3.13/macOS 14/arm64 的 `packaging.tags` 兼容集合有交集；
- 文件字节匹配 `uv.lock` SHA256；
- 不含 `libgfortran*`、`libgcc*`、`libquadmath*`、OpenBLAS 或 SciPy/NumPy 包目录；
- 每个包的名称、版本、大小、tags、原始 URL、SHA256 和许可证写入 `manifest.json`；
- 安装后的运行闭包与 manifest 一致，venv 自带 pip 不参与比较。

manifest 一致性拆分验证：位于 Subtap `libexec` 的 distributions 必须与 wheelhouse manifest 完全相等；外部批准集合只能是 NumPy 和 SciPy，并分别验证名称、版本约束、Cellar realpath 和 Formula identity。SentencePiece 0.2.2 属于 wheelhouse manifest，不能列为外部依赖。用户全局 site-packages 不进入 venv，也不参与比较。

`jieba==0.42.1` 仍是唯一允许的 source build：在无网络隔离环境使用锁定且校验过的 build-system wheels 构建，输入和输出全部纳入 SHA256 与 provenance。SentencePiece 只消费上游 wheel，不修改或重打包其字节；任何其他 sdist 或 native source build 立即终止。

## 许可证门禁

- 扫描剩余每个 wheel 的 METADATA、License-File、`.dist-info/licenses` 和 bundled component notices。
- AGPL、GPL、LGPL、未知或未识别许可证默认拒绝；书面审批前不能进入候选 Release。
- `licenses.json` 和 `THIRD_PARTY_LICENSES/` 随 wheelhouse 发布并成为 provenance subject。
- 自动检查 wheelhouse 中不存在 SciPy wheel、NumPy wheel和已知 GCC/OpenBLAS 动态库。
- Homebrew NumPy/SciPy 作为独立官方 Formula 依赖记录在 SBOM 中，但不复制到 Subtap Release。
- `sentencepiece==0.2.1` wheel 继续永久拒绝：当前 GitHub asset/锁文件 SHA256 是 `097f3394…`，但其 SLSA subject 对同名文件记录 `eb9c67ce…`，无法证明当前文件来自 attested build。
- `sentencepiece==0.2.2` 只允许上文固定的 wheel SHA。门禁必须调用锁定版本与 SHA256 的 OpenSSF `slsa-verifier`，以 `google/sentencepiece`、tag `v0.2.2` 验证官方 `multiple.intoto.jsonl`；仅自行解析 JSON 不算签名验证。
- 该 wheel 不修改字节，以保留 upstream hash 与 SLSA 身份。`THIRD_PARTY_LICENSES/` 作为同一 wheelhouse tar 的随附材料，至少包含 SentencePiece Apache-2.0、Abseil Apache-2.0、protobuf-lite BSD-3-Clause、darts-clone BSD-3-Clause、esaxx MIT 和 pybind11 BSD-3-Clause 全文；每份文本都记录精确 source URL、tag/commit 与 SHA256。Abseil 固定为 upstream CMake 声明的 `20260526.0`，pybind11 固定为 upstream run log 记录的 `3.0.4`；精确 hashes 以研究记录为准。
- `licenses.json` 把 wheel SHA、SLSA bundle SHA、source commit、全部许可证文本 SHA 和原生扫描结果绑定到同一记录。任何缺失、额外 native component、许可证不匹配或 hash 漂移立即终止。
- SLSA v0.2 predicate 明确声明 materials completeness 为 false，不能声称它证明了全部 build dependencies。已把同一 upstream run `29183857485` 的原始日志 archive identity、pybind11 3.0.4 与 `Not Found TCMalloc` 最小证据固化到 `docs/research/evidence/sentencepiece-v0.2.2-build-evidence.txt`（SHA256 `5cd0a8d2c1f617b7eaf52821132dc9655f13ec2b856e12d810b5c21f06a555e9`）；Release 还必须复制该证据到 provenance。它只补充许可证与 native 证据，不能冒充 SLSA materials 完整性。
- `slsa-verifier` 选型记录：OpenSSF 官方项目、Apache-2.0、当前约 337 Stars、近 6 个月仍有 commit；属于供应链验证细分工具。固定使用 `v2.7.1` Darwin arm64 binary，大小约 30.9 MiB、SHA256 `39abfcf5f1d690c3e889ce3d2d6a8b87711424d83368511868d414e8f8bcb05c`，只在构建 runner 使用，不进入用户安装包。

若剩余 wheel 仍包含禁止许可证组件，立即终止；不能通过换 Cask、CDN 或安装后下载绕过。

## 兼容性原型

原型在一次性 Sonoma arm64 runner 上执行：

1. 安装 Homebrew `python@3.13`、`numpy`、`scipy`、`ffmpeg`。
2. 记录 Formula 版本、revision、bottle SHA、Python patch、Homebrew 和 macOS 版本。
3. 创建普通 venv，并把 NumPy/SciPy 稳定 `opt` symlink 的 site-packages 字面路径写入 `.pth`，禁止写入带版本号的 Cellar realpath。
4. 下载锁文件指定的 SentencePiece 0.2.2 wheel、GitHub 同名 Release asset 和 `multiple.intoto.jsonl`；三方 SHA 必须等于 `201a8e0f…`，并使用固定 `slsa-verifier` 验证 source repo、tag 和 subject。
5. 从精确 source identities 收集六类许可证，生成 `licenses.json`；确认 wheel 本身没有被修改，且 notices 与 wheel 位于同一发布 tar。
6. 断言 `Path(numpy.__file__).resolve()`、`Path(scipy.__file__).resolve()` 分别位于 Homebrew NumPy/SciPy Cellar/opt_prefix，且 Subtap `libexec` 不含同名 distribution。
7. 安装剩余锁定 wheels，包括已验证的官方 SentencePiece wheel；断言 Python package 版本为 `0.2.2`。
8. 执行：

```bash
python -m pip check
python -c "import numpy, scipy, sentencepiece, mlx, mlx_audio, onnxruntime, torch, torchaudio"
subtap version
subtap doctor --json
```

9. 检查原生动态库和符号边界：wheelhouse 不得包含 SciPy/GCC/OpenBLAS 副本；SentencePiece extension 的 `otool -L` 只允许 macOS 系统库。精确拒绝 `libgcc*`、`libgfortran*`、`libquadmath*`、OpenBLAS、tcmalloc、libatomic 的文件路径、load command、archive member 和已知 runtime symbols；不得匹配裸 `GCC`，因为 Clang 生成的正常 `GCC_except_table*` 会造成误报。扫描结论与命令输出写入验收证据。
10. 使用本地测试模型运行最小 ASR/对齐 smoke；不把模型写入发布产物。

Doctor 只允许明确的模型缺失；`models_error`、ABI 错误、动态库错误或 `pip check` 失败立即终止。

## 版本漂移与升级

Homebrew 核心依赖是滚动更新的，不能把当前 patch 版本当作永久固定值：

- 每次 Subtap 发布都重新运行完整兼容验收；另设 scheduled 与 workflow_dispatch 监测 Homebrew 核心依赖漂移，发现版本、revision 或 bottle digest 变化即触发重验。
- 验收证据记录实际 NumPy、SciPy、Python、GCC 和 OpenBLAS 版本、revision 与 bottle digest；SentencePiece 记录 wheel、SLSA bundle、source commit 和许可证闭包 identity。
- Formula test 对公开兼容范围做断言，不偷偷锁定 Homebrew 不提供的旧 patch。
- Subtap 回滚不承诺回滚 Homebrew 核心依赖；必须证明上一 Subtap 候选仍能在当前 Homebrew 依赖上运行。
- Homebrew NumPy/SciPy 升级导致 ABI 或 API 不兼容时，停止发布并评估上游兼容范围，不在 Subtap 加载路径上打补丁。

## RC A/B 与 Tap 验收

首次载体验收使用连续 RC A/B：

1. A/B 固定快照验证必须在同一个一次性 runner 中完成：开头只安装一次 Homebrew Python、NumPy、SciPy、FFmpeg，随后设置 `HOMEBREW_NO_AUTO_UPDATE=1`、禁用 cleanup，A→B→A 全程不得 upgrade/reinstall 核心依赖。
2. 每个阶段比较 `brew list --versions`、Formula revision 和 bottle digest，身份必须完全一致。
3. A 在该固定快照上完成冷安装；B 在同一快照完成 A→B 升级与 B→A 回滚，版本必须精确等于 `EXPECTED_PREVIOUS_VERSION` 和 `EXPECTED_CANDIDATE_VERSION`。
4. B 的“最新依赖重验”在另一个全新 runner 中执行，不能复用固定快照 runner。
5. 候选 Formula 只进入固定 candidate commit，不预先污染 Tap 默认分支。
6. `brew audit --strict --online`、`brew install --build-from-source`、`brew test`、原生 import、最小 ASR/对齐 smoke 全部通过，且 GitHub `v0.2.2` Release 的 `prerelease` 已变为 false 后，载体 ADR 才能 Accepted。普通发布授权不能替代该稳定性门禁。

每个 RC 必须满足身份不变量：tag `vX`、pyproject/METADATA、Subtap wheel、wheelhouse 文件名、Formula version 和 Release target commit 完全一致；Release target 必须等于 tag peeled commit。wheelhouse tar、SHA256SUMS、manifest 和 licenses 都是 provenance subject。生成或安装 Formula 前执行 `gh attestation verify --repo R-jed/Subtap` 并核对 Release asset digest；同 tag 同名不同 digest 资产拒绝覆盖。A/B 的 tag、commit、Formula commit、URL 和 SHA256 全部写入验收 JSON。

正式 Release、Tap 默认分支原子更新和 README 解锁仍属于后续显式授权的正式发布门禁。

## 用户资料验收

开始前为以下路径写入不同内容的哨兵并记录 SHA256：

- `config.yaml`、`batch-config.yaml`、`state.json`
- `profile/`、`history/`
- `models/`、`glossaries/`、`manuscripts/`、`jobs/`

冷安装、升级、回滚和卸载后逐项复核。cache/logs 内容可变化，但不得删除整个 `~/.subtap` 或越界删除。

## 可观测性与证据

workflow 使用 `if: always()` 上传：

- Homebrew dependency versions、bottle SHA、brew config；
- wheelhouse manifest、licenses、体积和 attestation verify；
- Formula snapshot、Tap commit、audit/test/install/upgrade/rollback/uninstall 输出；
- pip check、import 路径、动态库路径、Doctor JSON、ASR/对齐 smoke；
- 用户资料哨兵校验结果。

每条命令保存 stdout、stderr 和 exit code，并生成机器可读 acceptance JSON。任何失败先保存证据再清理，且不能显示“验收通过”。

## 终止条件

以下任一情况立即停止该路线：

- venv 无法稳定导入 Homebrew NumPy/SciPy；
- Python 3.13 的 MLX/ONNX/Torch wheels 无法安装或加载；
- 剩余 wheels 触发许可证门禁；
- `uv.lock`、PyPI、GitHub asset 与 SLSA subject 的 SentencePiece SHA 任一不一致；
- SLSA 签名验证、source tag/commit、许可证闭包或原生扫描任一失败；
- GitHub `v0.2.2` Release 在正式发布时仍标记为 prerelease；
- pip check、动态库边界、严格审计或 Formula test 失败；
- 安装必须访问 PyPI、复制 Homebrew SciPy/GCC 文件或修改动态库路径；
- 当前 Homebrew 依赖无法同时支持 RC A/B；
- wheelhouse 超过 300 MiB 或 Subtap venv 超过 950 MiB。体积统一按 `1 MiB = 1,048,576 bytes` 计算；当前预估约 250 MiB / 878 MiB，只是进入原型的基线，不是通过证据。

终止后优先等待上游发布修正 provenance/许可证的稳定 wheel，或评估 MLX-Audio 移除 SentencePiece 依赖；不维护私有 SentencePiece fork，不自建 wrapper，也不依赖不可锁定的 Homebrew SentencePiece runtime。

## 非目标

- 不进入 homebrew/core。
- 不发布 Intel、Linux、Windows 或 macOS 13 包。
- 不重新分发 NumPy、SciPy、GCC、OpenBLAS。
- 不在本阶段创建正式 tag、发布 PyPI 正式版或更新 Tap 默认分支。
- 不维护私有 MLX-Audio fork。

## 参考

- [Homebrew SciPy Formula](https://github.com/Homebrew/homebrew-core/blob/HEAD/Formula/s/scipy.rb)
- [Homebrew NumPy Formula](https://github.com/Homebrew/homebrew-core/blob/HEAD/Formula/n/numpy.rb)
- [Homebrew Python Formula 指南](https://docs.brew.sh/Python-for-Formula-Authors)
- [Homebrew Tap 指南](https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap)
- [MLX-Audio 0.4.3 PyPI 元数据](https://pypi.org/pypi/mlx-audio/0.4.3/json)
- [SentencePiece v0.2.2 Release](https://github.com/google/sentencepiece/releases/tag/v0.2.2)
- [SentencePiece v0.2.2 LICENSE](https://raw.githubusercontent.com/google/sentencepiece/v0.2.2/LICENSE)
- [SentencePiece v0.2.2 Python build metadata](https://raw.githubusercontent.com/google/sentencepiece/v0.2.2/python/pyproject.toml)
- [SentencePiece v0.2.2 SLSA provenance](https://github.com/google/sentencepiece/releases/download/v0.2.2/multiple.intoto.jsonl)
- [OpenSSF slsa-verifier](https://github.com/slsa-framework/slsa-verifier)
