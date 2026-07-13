# Wheelhouse 许可证审查：SciPy 1.18.0

> 日期：2026-07-13  
> 范围：Subtap Apple Silicon / Python 3.12 Homebrew wheelhouse 候选  
> 结论性质：工程合规风险审查，**不是法律意见**。许可证解释和商业发布决定应由有资质的法律顾问确认。

## 决策摘要

**当前结论：拒绝发布该 wheelhouse；需要书面法律审批后才可重新评估。**

原因不是 SciPy 自身的 BSD-3-Clause，而是锁定的 macOS arm64 二进制 wheel 实际捆绑了：

- `libgfortran.5.dylib`、`libgcc_s.1.1.dylib`：`GPL-3.0-or-later WITH GCC-exception-3.1`；
- `libquadmath.0.dylib`：`LGPL-2.1-or-later`。

本项目规则要求禁止 GPL 类商业风险，并且设计规格明确规定 GPL、LGPL 及 GCC Runtime Library Exception 默认拒绝，只有书面审查明确批准后才能放行：[AGENTS.md:10](../../AGENTS.md#L10)、[设计规格:29-34](../superpowers/specs/2026-07-13-homebrew-wheelhouse-formula-design.md#L29-L34)。当前候选还没有可核验的、与这些二进制精确对应的 GCC 源码归档与构建信息，无法证明满足源码提供义务。

## 1. SciPy 为什么进入 Subtap 运行闭包

依赖链只有一条需要关注的主路径：

```text
Subtap
└── mlx-audio==0.4.3（Apple Silicon macOS）
    └── scipy>=1.10.0（无 extra 条件）
        └── scipy==1.18.0（Python >= 3.12 的锁定结果）
```

- Subtap 在 Apple Silicon macOS 上直接声明 `mlx-audio==0.4.3`：[pyproject.toml:28](../../pyproject.toml#L28)。
- MLX-Audio 0.4.3 的官方 PyPI 元数据把 `scipy>=1.10.0` 列为无条件运行依赖：[PyPI `requires_dist`](https://pypi.org/pypi/mlx-audio/0.4.3/json)。
- 本项目锁文件据此为 Python 3.12+ 选择 SciPy 1.18.0：[uv.lock:1251-1264](../../uv.lock#L1251-L1264)。候选 arm64 wheel、SHA256 与大小也被锁定：[uv.lock:2717](../../uv.lock#L2717)。
- Subtap 本身没有直接导入 SciPy；它通过 `mlx_audio.stt` 执行 ASR 和强制对齐。因此，直接删除 SciPy 会违反 MLX-Audio 已发布的依赖契约，并使规格要求的 `pip check` 失败。即使当前执行路径碰巧未导入 SciPy，也不能把“当前没触发”视为受支持的依赖裁剪。

## 2. 锁定 wheel 实际包含什么

审查对象为 PyPI 官方文件：

```text
scipy-1.18.0-cp312-cp312-macosx_14_0_arm64.whl
SHA256 9ab7b758be6940954a713ee466e2043e9f6e2ed965c1fce5c91039f4be3d90a9
```

该哈希与本地 `uv.lock` 以及 [SciPy 1.18.0 官方 PyPI 发布元数据](https://pypi.org/pypi/scipy/1.18.0/json)一致。对该精确文件解包得到：

| wheel 内文件 | wheel 内声明 | 作用 |
|---|---|---|
| `scipy/.dylibs/libgfortran.5.dylib` | GPL-3.0-or-later WITH GCC-exception-3.1 | Fortran 运行时 |
| `scipy/.dylibs/libgcc_s.1.1.dylib` | GPL-3.0-or-later WITH GCC-exception-3.1 | GCC 运行时 |
| `scipy/.dylibs/libquadmath.0.dylib` | LGPL-2.1-or-later | 四倍精度数学运行时 |

证据来自该 wheel 自带的 `scipy-1.18.0.dist-info/LICENSE.txt`：它将 `libgfortran*`、`libgcc*` 标为 `GPL-3.0-or-later WITH GCC-exception-3.1`，将 `libquadmath*` 标为 `LGPL-2.1-or-later`，并附带许可证全文。精确 wheel 下载地址记录在 [uv.lock:2717](../../uv.lock#L2717)。

SciPy 项目源码本身仍是 BSD-3-Clause；源码许可证允许带条件地以源码或二进制形式再分发：[SciPy v1.18.0 `LICENSE.txt`](https://github.com/scipy/scipy/blob/v1.18.0/LICENSE.txt)。二进制 wheel 的内置组件通知是额外义务，不能只看 SciPy 顶层 BSD classifier。

## 3. wheelhouse 再分发的义务

以下是基于官方许可证文本的保守工程解释，最终应由法律顾问确认。

### 3.1 通知和许可证文本

- SciPy BSD-3-Clause 要求二进制再分发在文档或随附材料中保留版权通知、条件和免责声明：[SciPy v1.18.0 许可证](https://github.com/scipy/scipy/blob/v1.18.0/LICENSE.txt)。
- LGPL 2.1 第 1、6 节要求保留许可证、显著说明使用该库并告知用户其权利：[GNU LGPL 2.1](https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html#SEC1)。
- GPLv3 第 4、6 节要求保留法律通知和 GPL 文本，并在传递目标码时以许可证允许的方式提供 Corresponding Source：[GNU GPLv3 §4-6](https://www.gnu.org/licenses/gpl-3.0.html#section6)。

因此，Formula 安装时不能删除 SciPy `.dist-info/LICENSE.txt`；wheelhouse 的 `licenses.json` 和 Release 页面也应显式列出三个 GCC 运行时组件，而不能只写 “SciPy: BSD”。

### 3.2 源码提供

- `libquadmath` 是 wheel 内直接传递的 LGPL 目标码。LGPL 2.1 第 4 节要求随目标码提供完整、机器可读的对应源码，网络下载场景可在同一位置提供等价源码访问：[GNU LGPL 2.1 §4](https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html#section4)。
- SciPy 扩展与 `libquadmath` 动态链接。LGPL 2.1 第 6 节还要求允许用户为自身使用修改和为调试修改而逆向工程，并满足可重新链接/替换库的条件。第 6(b) 的“系统已有共享库”路径不适合当前候选，因为 wheel 自己复制了该 dylib；保守路径是提供对应源码及可替换机制：[GNU LGPL 2.1 §6](https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html#section6)。
- `libgfortran` 和 `libgcc` 带 GCC Runtime Library Exception。该例外允许通过合格编译过程生成的 Target Code 与独立模块组合，并允许组合体使用自选条款；其目的明确包括让非 GPL/专有程序使用 GCC 运行时：[GCC Runtime Library Exception §1](https://www.gnu.org/licenses/gcc-exception-3.1.html)。
- 但该例外也明确不产生“第三方软件当然不受 GCC copyleft 影响”的一般推定。它放宽的是 Target Code 组合的许可，不明确免除对 **Runtime Library 本身目标码** 的 GPLv3 第 6 节源码提供义务：[GCC Runtime Library Exception §2](https://www.gnu.org/licenses/gcc-exception-3.1.html)、[GNU GPLv3 §6](https://www.gnu.org/licenses/gpl-3.0.html#section6)。这是本报告的保守推论，必须由法律顾问确认。

当前 wheel 的通知只给出 GCC 仓库目录，没有记录构建这些 dylib 的精确 GCC tag/commit、补丁和构建脚本。一个泛化源码仓库链接不足以证明它就是 GPL/LGPL 所称的 Corresponding Source。因此在 Release 同时提供精确、可长期访问的源码与构建材料前，wheelhouse 不应发布。

### 3.3 替换和修改能力

当前 wheel 使用独立 `.dylib` 并通过动态链接加载，从技术形态上比静态合入更容易替换；但发布方仍需确认：

1. 安装条款不禁止用户修改或为调试修改而逆向工程；
2. 安装后的文件权限和布局允许用户用接口兼容版本替换 `libquadmath`；
3. 提供与精确二进制对应的源码及必要构建信息；
4. 修改后的 LGPL/GPL 组件继续按其许可证分发，并标明修改。

只保留 wheel 内的许可证全文，不自动满足以上全部义务。

## 4. 在项目政策下能否批准

| 判断 | 结论 |
|---|---|
| 技术上是否能与 MIT Subtap 一起运行 | GCC Exception 和 LGPL 原则上允许非 GPL 程序使用这些动态库，但需满足各自条件。 |
| 是否会自动把 Subtap 改成 GPL | 没有证据支持这一结论；聚合不会自动把独立部分变成 GPL，GCC Exception 也专门允许符合条件的组合使用自选条款。[GPLv3 §5](https://www.gnu.org/licenses/gpl-3.0.html#section5)、[GCC Exception §1](https://www.gnu.org/licenses/gcc-exception-3.1.html) |
| 当前 wheelhouse 是否已有充分合规证据 | 否。缺少精确 Corresponding Source、构建对应关系和书面审批。 |
| 项目团队是否可自行批准 | 否。项目规则和已确认规格均把 GPL/LGPL/GCC Exception 设为书面审查硬门禁。 |
| 发布门禁 | **拒绝（blocked）**，直到有资质法律顾问书面批准具体分发方案，且发布资产实际提供其要求的通知、源码和替换材料。 |

书面审批至少应回答：GCC Exception 是否免除本场景对运行库本体的哪些义务、SciPy wheel 的动态链接是否满足 LGPL 6、应提供哪一版本 GCC 的哪些源码/构建脚本、Tap/Release 各自是否构成传递主体，以及需要保留多久。

## 5. 不分发该 wheel 能否避免义务

### 可显著降低直接再分发义务的路径

1. **上游移除/可选化 SciPy：** 若 MLX-Audio 发布新版本，把 SciPy 从无条件运行依赖移除，并且 Subtap 的完整 ASR/对齐测试与 `pip check` 均通过，则 SciPy 可退出闭包。这是最干净的路径；当前 0.4.3 不满足。
2. **从源码构建 SciPy，动态使用 Homebrew 独立提供的 GCC 运行库：** Subtap 自己的 Release 不再捆绑这些 dylib，可把 GCC 组件的分发责任交给相应 Homebrew Formula。但这改变已确认的离线 wheelhouse 方案，并需另行验证 Homebrew 和 MLX 的构建兼容性。
3. **不发布 Homebrew 载体，只发布 Subtap 自身的 MIT wheel：** 用户自行从上游获取 MLX-Audio/SciPy 时，Subtap Release 不再承载这些二进制；代价是失去当前“一条命令、离线闭包”的产品目标。

### 不能消除义务或仍需法律确认的路径

- **改用 Cask 但仍内置相同 wheel：** 不改变被再分发的字节，义务不变。
- **把 wheel 从 Subtap Release 移到另一个自有仓库/CDN：** 只是更换托管位置，不改变发布方传递目标码的事实。
- **Formula 直接链接 PyPI wheel：** 可减少 Subtap 自己托管二进制的事实，但 Formula 明确促成用户取得该文件是否构成法律意义上的 conveyance，需要法律顾问确认；同时它违反已确认的离线 wheelhouse 设计，不能作为无审批捷径。
- **用 `--no-deps` 忽略 SciPy：** 会破坏 MLX-Audio 的官方依赖契约和 `pip check`，属于隐藏问题，不接受。

## 最终门禁

在以下四项同时满足前，不得生成或发布正式 Formula，也不得把载体 ADR 改为 Accepted：

1. 法律顾问对 **这个精确 SciPy wheel** 给出书面批准；
2. Release 与 wheelhouse 保留并公开完整许可证/通知；
3. Release 提供法律顾问确认的精确 Corresponding Source、构建信息和必要替换材料，并受 SHA256 与 attestation 覆盖；
4. 自动化测试证明安装后许可证可见、源码链接有效、用户能替换接口兼容的 LGPL 库，并且升级/回滚不丢失这些材料。

若不准备承担这些工作，应终止 wheelhouse Formula 路线，选择不再分发该 SciPy wheel 的架构，而不是降低扫描门禁。

## 补充：Homebrew 托管科学计算栈路线的 SentencePiece 阻塞

改由 Homebrew Formula 提供 NumPy/SciPy 后，SciPy/GCC 再分发问题退出 Subtap wheelhouse；但锁定的 `sentencepiece==0.2.1` CPython 3.13 arm64 wheel 仍缺少 wheel 内许可证文件和标准许可证元数据。

- 锁文件 SHA256：`097f3394e99456e9e4efba1737c3749d7e23563dd1588ce71a3d007f25475fff`。
- PyPI 文件：[sentencepiece-0.2.1-cp313-cp313-macosx_11_0_arm64.whl](https://files.pythonhosted.org/packages/8d/de/5a007fb53b1ab0aafc69d11a5a3dd72a289d5a3e78dcf2c3a3d9b14ffe93/sentencepiece-0.2.1-cp313-cp313-macosx_11_0_arm64.whl)。
- 上游 `v0.2.1` tag 指向 GitHub verified commit `31646a4`：[GitHub Release](https://github.com/google/sentencepiece/releases/tag/v0.2.1)。
- PyPI Integrity API 对该精确 wheel 返回 `404 Not Found`：[provenance endpoint](https://pypi.org/integrity/sentencepiece/0.2.1/sentencepiece-0.2.1-cp313-cp313-macosx_11_0_arm64.whl/provenance)。按 PyPI 文档，404 表示该文件没有 provenance：[Integrity API](https://docs.pypi.org/api/integrity/#status-codes)。

因此现有证据能证明“官方项目有 Apache-2.0 许可证，且 tag 指向 GitHub verified source commit”，但不能证明“这个精确二进制 wheel 由该 source 构建”。按当前设计的精确 wheel→source 门禁，该路线必须停止；代理不能用项目自写 JSON 冒充上游 provenance 或人工审批。

### 成熟方案复用评估与已确认方向

进一步检查官方 GitHub Release 后发现，不能只以 PyPI Integrity API 判断 upstream provenance。SentencePiece 自己发布了 OpenSSF SLSA bundle，但两个版本的结果不同：

- `v0.2.1` GitHub/PyPI/锁文件的 CPython 3.13 arm64 wheel SHA256 是 `097f3394e99456e9e4efba1737c3749d7e23563dd1588ce71a3d007f25475fff`，而 SLSA subject 对同名文件记录 `eb9c67ce534905cd262b608980de63474de8e9a7a02715c44a974fc11307212b`。名称相同但字节不匹配，仍然拒绝。
- `v0.2.2` GitHub Release 与 PyPI 的同名 CPython 3.13 arm64 wheel 大小均为 1,347,267 bytes，SHA256 均为 `201a8e0f55501a76e08dbf2c54bc45f4642b379271e89c667d517bfbc2191f2a`。
- `v0.2.2` SLSA subject 精确记录同一 SHA，config source 为 tag `v0.2.2`、commit `e0cce7d37b065b5140349dbe12c6bcf6192fdd78`、workflow `.github/workflows/wheel.yml`。bundle 自身 SHA256 为 `cc6f6011e50a3ed6099e0cdfe59ae517c16d2b40c74de76eebaa8e8426f0486b`。
- GitHub 把 `v0.2.2` 标记为 prerelease，但 PyPI 与 Homebrew 均使用无预发布后缀的 0.2.2。该差异必须公开记录，当前只进入 RC 验证。

对精确 wheel 解包检查：`METADATA` 有 `License-Expression: Apache-2.0`，wheel 内没有 LICENSE/NOTICE；唯一 native member 为 `_sentencepiece.cpython-313-darwin.so`，`otool -L` 只列出 macOS `libc++.1.dylib` 与 `libSystem.B.dylib`。这说明 wheel 静态包含 SentencePiece 实现，外部不存在会随 Homebrew 滚动漂移的 SentencePiece ABI，但发布方必须补齐随附许可证通知。

固定许可证闭包至少包括：SentencePiece Apache-2.0、Abseil Apache-2.0、protobuf-lite BSD-3-Clause、darts-clone BSD-3-Clause、esaxx MIT、pybind11 BSD-3-Clause。通知作为同一 wheelhouse tar 的 `THIRD_PARTY_LICENSES/`，每份文本固定 source URL、tag/commit 和 SHA256；wheel 本身不得修改，否则 upstream SLSA 身份失效。

现场固定的许可证文件身份如下：

| 组件 | source identity | LICENSE SHA256 |
|---|---|---|
| SentencePiece | `v0.2.2` / `e0cce7d37b065b5140349dbe12c6bcf6192fdd78` | `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` |
| protobuf-lite | SentencePiece `v0.2.2/third_party/protobuf-lite` | `6e5e117324afd944dcf67f36cf329843bc1a92229a8cd9bb573d7a83130fea7d` |
| darts-clone | SentencePiece `v0.2.2/third_party/darts_clone` | `155f59997298ee336602c49f9c1110f268ac394ca2197eb02647a3555935ad52` |
| esaxx | SentencePiece `v0.2.2/third_party/esaxx` | `7c28553d1d3312d65fe309f76a22ebaf33a3d76c8c1e3b98a88ee4654ecb53db` |
| Abseil | `20260526.0` / `5650e9cf76d3be4318d5fa3af38ee483ddfd5e4a` | `c79a7fea0e3cac04cd43f20e7b648e5a0ff8fa5344e644b0ee09ca1162b62747` |
| pybind11 | upstream run log resolves `3.0.4` / `d03662f0984f652b60e7ddce53d3868002275197` | `83965b843b98f670d3a85bd041ed4b372c8ec50d7b4a5995a83ac697ba675dcb` |

上游 macOS build log 明确记录 `Not Found TCMalloc: TCMALLOC_LIB-NOTFOUND`；结合 wheel 的动态库结果与后续符号/字符串扫描，作为没有额外 tcmalloc/GCC runtime 的证据。若实现阶段发现更多组件，必须扩大许可证闭包，不能沿用这张表静默放行。

最终方向改为直接复用这个精确的官方 0.2.2 wheel。现场使用 OpenSSF `slsa-verifier` v2.7.1 验证 source repo `google/sentencepiece` 与 tag `v0.2.2`，输出确认 builder、commit `e0cce7d…` 和 artifact 全部通过。后续构建门禁必须重复签名、source repo、tag 与 subject 验证，再核对锁文件、GitHub、PyPI 和许可证记录的 SHA。`slsa-verifier` 是 Apache-2.0 的 OpenSSF 细分工具，约 337 Stars，近 6 个月仍有 commit；固定的 Darwin arm64 binary 为 32,395,890 bytes、SHA256 `39abfcf5f1d690c3e889ce3d2d6a8b87711424d83368511868d414e8f8bcb05c`，只在 runner 使用。

SLSA predicate 的 `completeness.materials=false`，不能证明完整 build-dependency 闭包。GitHub Actions run `29183857485` 的 log archive 大小为 1,085,946 bytes、SHA256 `f914011769b9013795457cc8719fb015af698fa4e527dc0c35cea1155871e62b`；其中记录 macOS job 使用 pybind11 3.0.4，并两次输出 `Not Found TCMalloc`。最小证据已固化到 [sentencepiece-v0.2.2-build-evidence.txt](evidence/sentencepiece-v0.2.2-build-evidence.txt)，SHA256 为 `5cd0a8d2c1f617b7eaf52821132dc9655f13ec2b856e12d810b5c21f06a555e9`。该证据用于保守补齐 notices，不得表述为 SLSA 完整材料证明。

许可证不能只存在于下载 tar：Formula 必须把 `licenses.json` 与 `THIRD_PARTY_LICENSES/` 安装进 Cellar 的 `pkgshare`，Formula test 校验存在性与 SHA，确保未来生成 Homebrew bottle 时通知仍随二进制分发。

以下两条路线淘汰：

- 自建完整 static wheel：重复上游已提供且已有 SLSA 的二进制，还扩大 Abseil/protobuf-lite/darts/esaxx、tcmalloc/libatomic 和非密封脚本的审查面。
- Homebrew C++ runtime + 自建 wrapper：upstream setup.py 不支持该路径，Homebrew bottle 又缺少 wrapper 编译所需的 Abseil headers；同时非 versioned Formula 无法保证旧 Subtap Release 的 ABI。继续补丁化兼容违反项目根因修复原则。

该方案只有在签名验证、完整 notices、native 扫描和真实运行验收全部通过后才能进入候选 Release；否则仍保持 blocked。
