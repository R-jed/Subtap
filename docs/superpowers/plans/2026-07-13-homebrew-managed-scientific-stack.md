# Homebrew 托管科学计算栈实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 生成只包含锁定非科学计算依赖的 Apple Silicon wheelhouse，让 Homebrew 官方 NumPy/SciPy 提供科学计算栈，并用可重复证据验证安装、升级、回滚和用户资料保留。

**架构：** 单个 Python 构建器负责从 `uv.lock` 导出 Python 3.13/macOS arm64 运行闭包、下载并校验 wheels、执行许可证与动态库门禁、生成 manifest 和离线 requirements。现有 RC Release workflow 生成版本化 wheelhouse tar、上传并证明来源；Formula 只消费固定 tag 的不可变 HTTPS 资产，普通 venv 通过稳定 `opt` 路径精确接入 Homebrew NumPy/SciPy。现有 `homebrew_acceptance.sh` 在不推送的隔离本地 Tap 中执行 A→B→A 固定依赖快照验收，独立 carrier workflow 只消费已存在的两个 RC，不修改 Tap 远端默认分支。

**技术栈：** Python 3.13 标准库、uv、pip、Homebrew Formula、Ruby、Bash、pytest、GitHub Actions、GitHub artifact attestations。

**状态：** Superseded，禁止继续执行。更新后的候选改为复用带官方 SLSA provenance 的 `sentencepiece==0.2.2` CPython 3.13 arm64 wheel，并随附完整第三方许可证通知；本计划将在书面规格获批后重写，现有任务 2-7 仍不得开始。

---

## 文件结构

- 创建：`scripts/homebrew_wheelhouse.py` — 构建并验证锁定 wheelhouse、manifest、许可证和离线 requirements；避免与第三方 `packaging` 包重名。
- 创建：`packaging/homebrew/license-policy.json` — 精确 wheel SHA 对应的许可证审批与来源证据。
- 条件创建：`packaging/homebrew/third-party/sentencepiece-LICENSE` — 只在精确 wheel provenance 与人工审批通过后收录 SentencePiece 官方 Apache-2.0 文本；当前不创建。
- 创建：`packaging/homebrew/subtap.rb.in` — 使用 Homebrew NumPy/SciPy 的唯一 Formula 模板。
- 条件创建：`packaging/homebrew/carrier-baseline.json` — 首次真实 A/B 成功并经人工审查后保存定时漂移监测的唯一不可变输入；当前 Blocked 阶段不得伪造。
- 创建：`scripts/render_homebrew_formula.py` — 严格校验版本、URL、SHA 后渲染候选 Formula。
- 创建：`tests/test_homebrew_wheelhouse.py` — wheel 选择、哈希、许可证、禁止组件、manifest 测试。
- 创建：`tests/test_homebrew_formula.py` — Formula 依赖、稳定 `.pth`、离线安装和身份测试。
- 修改：`scripts/homebrew_acceptance.sh` — 固定依赖快照、精确版本、结构化证据和完整哨兵。
- 修改：`tests/test_release_safety.py` — 验收脚本与 workflow fail-fast 门禁测试。
- 修改：`.github/workflows/release.yml` — 为后续 RC 构建、证明并上传版本化 wheelhouse 资产。
- 创建：`.github/workflows/homebrew-carrier.yml` — 手动/定时原型和依赖漂移验证。
- 修改：`scripts/check.sh` — 纳入新静态测试，不执行破坏性 Homebrew 验收。
- 修改：`docs/adr/0001-homebrew-distribution-carrier.md` — 记录候选实现状态和仍需真实 RC 证据的边界。

## 任务 1：建立 wheel 许可证与来源门禁

**文件：**
- 创建：`scripts/homebrew_wheelhouse.py`
- 创建：`packaging/homebrew/license-policy.json`
- 创建：`packaging/homebrew/third-party/sentencepiece-LICENSE`
- 创建：`tests/test_homebrew_wheelhouse.py`

- [x] **步骤 1：编写失败测试**

```python
def test_sentencepiece_requires_exact_approved_hash(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, "sentencepiece", "0.2.1", license_text=None)
    with pytest.raises(WheelhouseError, match="unapproved wheel hash"):
        inspect_wheel(wheel, {"wheel_approvals": {}})


def test_rejects_forbidden_bundled_library(tmp_path: Path) -> None:
    wheel = make_wheel(
        tmp_path,
        "example",
        "1.0",
        license_text="MIT",
        extra={"example/.dylibs/libgfortran.5.dylib": b"binary"},
    )
    with pytest.raises(WheelhouseError, match="libgfortran"):
        inspect_wheel(wheel, {"allowed_licenses": ["MIT"]})


@pytest.mark.parametrize("location", ["License-File", ".dist-info/licenses/COPYING", "NOTICE"])
def test_rejects_gpl_or_lgpl_in_all_license_locations(tmp_path: Path, location: str) -> None:
    wheel = make_wheel_with_license_location(tmp_path, location, "GNU Lesser General Public License")
    with pytest.raises(WheelhouseError, match="forbidden license"):
        inspect_wheel(wheel, approved_policy())


def test_missing_license_and_changed_approved_hash_fail(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, "sentencepiece", "0.2.1", license_text=None)
    with pytest.raises(WheelhouseError):
        inspect_wheel(wheel, approved_policy(hash="0" * 64))


def test_license_bundle_hashes_match_manifest(tmp_path: Path) -> None:
    manifest = build_fixture_wheelhouse(tmp_path, packages=("approved",))
    license_record = manifest["licenses"][0]
    assert sha256_file(tmp_path / license_record["path"]) == license_record["sha256"]
```

- [x] **步骤 2：确认测试因实现缺失而失败**

运行：`uv run pytest -q tests/test_homebrew_wheelhouse.py`

预期：FAIL，`scripts/homebrew_wheelhouse.py` 尚不存在。

- [x] **步骤 3：实现最小检查器**

```python
FORBIDDEN_MEMBERS = ("libgfortran", "libgcc", "libquadmath", "openblas")
FORBIDDEN_LICENSES = ("AGPL", "GPL", "LGPL")


def inspect_wheel(path: Path, policy: dict[str, object]) -> WheelRecord:
    digest = sha256_file(path)
    with ZipFile(path) as archive:
        names = archive.namelist()
        forbidden = next((n for n in names if any(x in n.lower() for x in FORBIDDEN_MEMBERS)), None)
        if forbidden:
            raise WheelhouseError(f"forbidden bundled component: {forbidden}")
        metadata_name = require_single(names, ".dist-info/METADATA")
        metadata = message_from_bytes(archive.read(metadata_name))
        license_id = normalized_license(metadata, names, archive)
    if license_id == "UNKNOWN":
        raise WheelhouseError(f"unapproved wheel hash: {digest}")
    if any(token in license_id.upper() for token in FORBIDDEN_LICENSES):
        raise WheelhouseError(f"forbidden license: {license_id}")
    return WheelRecord.from_metadata(path, digest, metadata, license_id)
```

构建器先为 SentencePiece arm64 CPython 3.13 wheel SHA `097f3394e99456e9e4efba1737c3749d7e23563dd1588ce71a3d007f25475fff` 生成证据请求，至少包含 PyPI 文件 URL、PyPI Integrity API 结果、官方 `v0.2.1` tag/GitHub verified commit、Apache-2.0 LICENSE URL、审批人和审批日期。当前 PyPI Integrity API 返回 404，不能证明该 wheel 与 verified source commit 的对应关系，因此不得由代理创建批准项或继续任务 2。只有 wheel→source provenance 可以本地确定性验证后，才能另行设计并评审批准通道；当前实现不读取 `wheel_approvals` 来放行未知许可证，任何未知许可证一律失败。

任务 1 的交付物只是“默认拒绝”的门禁实现和 Blocked 证据。步骤 4 测试 PASS 只证明未知/未获批 wheel 会被拒绝，不代表 SentencePiece 已通过许可证门禁；提交任务 1 后必须停止，任务 2-7 不执行。

- [x] **步骤 4：验证绿灯并提交**

运行：`uv run pytest -q tests/test_homebrew_wheelhouse.py`

预期：PASS。

```bash
git add scripts/homebrew_wheelhouse.py packaging/homebrew tests/test_homebrew_wheelhouse.py
git commit -m "build: 建立 wheel 许可证门禁（任务 1/7）" -m "问题或需求描述：剩余 wheel 必须有精确来源、许可证和禁止组件证据。" -m "修复或实现思路：按文件 SHA fail-fast 审批并扫描元数据、许可证和捆绑动态库。"
```

## 任务 2：构建锁定的 Python 3.13 arm64 wheelhouse

**文件：**
- 修改：`scripts/homebrew_wheelhouse.py`
- 修改：`tests/test_homebrew_wheelhouse.py`

- [ ] **步骤 1：编写失败测试**

```python
def test_manifest_excludes_homebrew_scientific_stack(tmp_path: Path) -> None:
    manifest = build_fixture_wheelhouse(tmp_path, packages=("subtap", "mlx", "numpy", "scipy"))
    assert {item["name"] for item in manifest["packages"]} == {"subtap", "mlx"}
    assert [item["name"] for item in manifest["external_packages"]] == ["numpy", "scipy"]


def test_requirements_are_hash_locked_and_offline(tmp_path: Path) -> None:
    manifest = build_fixture_wheelhouse(tmp_path, packages=("subtap", "mlx"))
    text = (tmp_path / "requirements.txt").read_text()
    assert "subtap==" in text and "mlx==" in text
    assert text.count("--hash=sha256:") == len(manifest["packages"])
    assert "http://" not in text and "https://" not in text


def test_external_packages_have_constraints_and_formula_identity(tmp_path: Path) -> None:
    manifest = build_fixture_wheelhouse(tmp_path, packages=("mlx-audio",))
    assert manifest["external_packages"] == [
        {"name": "numpy", "requirement": ">=1.26.4", "formula": "numpy"},
        {"name": "scipy", "requirement": ">=1.10.0", "formula": "scipy"},
    ]
```

- [ ] **步骤 2：确认测试正确失败**

运行：`uv run pytest -q tests/test_homebrew_wheelhouse.py -k 'manifest or requirements'`

预期：FAIL，构建入口尚未实现。

- [ ] **步骤 3：实现构建命令**

```bash
uv run python scripts/homebrew_wheelhouse.py build \
  --python-version 3.13 \
  --platform macosx_14_0_arm64 \
  --output dist/homebrew-wheelhouse
```

构建器必须：

1. 执行 `uv export --frozen --no-dev --no-emit-project --no-emit-package numpy --no-emit-package scipy`；
2. 用 CPython 3.13/macOS arm64 下载与 `uv.lock` SHA 匹配的 wheels；仅 `jieba==0.42.1` 允许从锁定 sdist 在隔离环境构建；
3. 加入当前构建的 Subtap wheel；
4. 对每个 wheel 调用任务 1 的检查器；
5. `external_packages` 为 NumPy/SciPy 分别记录合并后的版本约束、Homebrew Formula identity 和实际 Cellar 版本校验要求；
6. 输出 `wheels/`、`requirements.txt`、`manifest.json`、`licenses.json`、`THIRD_PARTY_LICENSES/` 和 `SHA256SUMS`；
7. 读取 manifest 的 `subtap_version` 生成 `subtap-{subtap_version}-py313-macos-arm64-wheelhouse.tar.gz`，并固定排序、mtime、uid/gid 和 mode；两次真实构建的最终 tar SHA 必须相同；
8. 总体积超过 `300 MiB` 时退出非零。

`jieba==0.42.1` 必须从 `uv.lock` 的 sdist SHA 构建。先从 sdist 的 `pyproject.toml`/legacy setup 元数据读取实际 build requirements，把对应 wheels 的 URL 与 SHA 写入 build manifest；设置固定 `SOURCE_DATE_EPOCH`，在两次全新无网络目录中构建并规范化 wheel ZIP 时间、顺序和 mode，最终 wheel SHA 必须相同。fixture 构建不能替代这项真实验证。

- [ ] **步骤 4：验证可复现性并提交**

运行两次 fixture 构建并比较：`uv run pytest -q tests/test_homebrew_wheelhouse.py`

预期：PASS，排序、JSON 和 tar 输入均稳定。

```bash
git add scripts/homebrew_wheelhouse.py tests/test_homebrew_wheelhouse.py
git commit -m "build: 生成锁定 Homebrew wheelhouse（任务 2/7）" -m "问题或需求描述：Formula 不能运行时访问 PyPI，也不能携带 NumPy/SciPy 副本。" -m "修复或实现思路：从 uv.lock 生成 Python 3.13 arm64 的精确离线运行闭包。"
```

## 任务 3：渲染只接入 Homebrew NumPy/SciPy 的 Formula

**文件：**
- 创建：`packaging/homebrew/subtap.rb.in`
- 创建：`scripts/render_homebrew_formula.py`
- 创建：`tests/test_homebrew_formula.py`

- [ ] **步骤 1：编写失败测试**

```python
def test_formula_uses_stable_opt_paths_and_offline_pip(tmp_path: Path) -> None:
    formula = render_fixture(tmp_path)
    assert 'depends_on "python@3.13"' in formula
    assert 'depends_on "numpy"' in formula
    assert 'depends_on "scipy"' in formula
    assert 'Formula["numpy"].opt_lib/"python3.13/site-packages"' in formula
    assert 'Formula["scipy"].opt_lib/"python3.13/site-packages"' in formula
    assert "realpath" not in formula.split(".pth")[0]
    assert "--no-index" in formula
    assert "--require-hashes" in formula
    assert "--no-deps" in formula
    assert "--only-binary=:all:" in formula


def test_renderer_rejects_mismatched_version(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="version mismatch"):
        render_formula(version="0.1.0rc3", manifest={"subtap_version": "0.1.0rc2"})
```

- [ ] **步骤 2：确认测试正确失败**

运行：`uv run pytest -q tests/test_homebrew_formula.py`

预期：FAIL，模板与渲染器尚不存在。

- [ ] **步骤 3：实现最小 Formula**

模板声明 `arm64`、Sonoma、`python@3.13`、`numpy`、`scipy`、`ffmpeg`；普通 venv 的 `.pth` 写入两个稳定 `opt_lib` 字面路径。安装只执行：

```ruby
system python, "-m", "pip", "install",
  "--no-index", "--find-links", buildpath/"wheels", "--no-deps",
  "--require-hashes", "--only-binary=:all:", "-r", buildpath/"requirements.txt"
```

`test do` 验证 `subtap version`、`python -m pip check`、Doctor JSON、`mlx`/`mlx_audio`/`onnxruntime`/`torch`/`torchaudio` import、NumPy/SciPy 版本约束和实际路径位于各自 `opt_prefix.realpath`，并确认 `libexec` 没有本地 NumPy/SciPy distribution。

- [ ] **步骤 4：验证并提交**

运行：`uv run pytest -q tests/test_homebrew_formula.py`

预期：PASS。

```bash
git add packaging/homebrew/subtap.rb.in scripts/render_homebrew_formula.py tests/test_homebrew_formula.py
git commit -m "build: 渲染 Homebrew 科学计算依赖 Formula（任务 3/7）" -m "问题或需求描述：Subtap 需要复用 Homebrew 科学计算栈且隔离用户全局 Python。" -m "修复或实现思路：普通 venv 仅通过稳定 opt 路径接入 NumPy/SciPy，其他依赖全部离线安装。"
```

## 任务 4：让后续 RC 发布版本化 wheelhouse 并生成来源证明

**文件：**
- 修改：`.github/workflows/release.yml`
- 修改：`tests/test_release_safety.py`

- [ ] **步骤 1：编写失败测试**

```python
def test_release_attests_complete_versioned_wheelhouse() -> None:
    text = (ROOT / ".github/workflows/release.yml").read_text()
    workflow = yaml.safe_load(text)
    assert "homebrew-wheelhouse" in workflow["jobs"]
    assert "subtap-${{ needs.metadata.outputs.version }}-py313-macos-arm64-wheelhouse.tar.gz" in text
    for subject in ("manifest.json", "licenses.json", "SHA256SUMS"):
        assert subject in text
    assert "actions/attest-build-provenance" in text
    assert "gh attestation verify" in text
```

- [ ] **步骤 2：确认测试失败**

运行：`uv run pytest -q tests/test_release_safety.py -k wheelhouse`

预期：FAIL，现有 Release 只发布 Python wheel/sdist。

- [ ] **步骤 3：扩展现有 RC workflow**

新增 Apple Silicon `homebrew-wheelhouse` job，在任务 1 许可证审批存在时执行真实 wheelhouse 双构建与 SHA 比较。验证 tag、peeled commit、`pyproject.toml`、wheel METADATA、Subtap wheel、wheelhouse 文件名和 manifest 版本完全一致；版本化 tar、外层 SHA256SUMS、manifest、licenses 和 THIRD_PARTY_LICENSES 全部作为 attestation subjects。`github-release` 仅在 attestation 完成后上传这些资产；RC 仍标记 prerelease，PyPI 继续跳过。workflow 不生成 tag，只有未来显式授权创建的新 RC tag 才触发。

- [ ] **步骤 4：验证并提交**

运行：`uv run pytest -q tests/test_release_safety.py`

预期：PASS。

```bash
git add .github/workflows/release.yml tests/test_release_safety.py
git commit -m "ci: 发布并证明 Homebrew wheelhouse（任务 4/7）" -m "问题或需求描述：Formula 必须消费不可变 HTTPS 资产，不能用本地目录冒充真实安装。" -m "修复或实现思路：未来 RC 生成版本化 wheelhouse、完整身份校验和 GitHub provenance。"
```

## 任务 5：把现有 Homebrew 验收器升级为固定快照 A→B→A

**文件：**
- 修改：`scripts/homebrew_acceptance.sh`
- 修改：`tests/test_release_safety.py`

- [ ] **步骤 1：编写失败测试**

```python
def test_homebrew_acceptance_freezes_dependency_snapshot() -> None:
    text = (ROOT / "scripts/homebrew_acceptance.sh").read_text()
    assert "HOMEBREW_NO_AUTO_UPDATE=1" in text
    assert "HOMEBREW_NO_INSTALL_CLEANUP=1" in text
    assert "EXPECTED_PREVIOUS_VERSION" in text
    assert "EXPECTED_CANDIDATE_VERSION" in text
    assert "acceptance.json" in text
    assert "brew list --versions python@3.13 numpy scipy gcc openblas ffmpeg" in text
    assert "bottle" in text and "revision" in text


def test_homebrew_acceptance_preserves_all_user_records() -> None:
    text = (ROOT / "scripts/homebrew_acceptance.sh").read_text()
    for name in ("config.yaml", "batch-config.yaml", "state.json", "profile", "history"):
        assert name in text
```

- [ ] **步骤 2：确认测试失败**

运行：`uv run pytest -q tests/test_release_safety.py -k homebrew_acceptance`

预期：FAIL，现有脚本没有完整固定快照与证据 JSON。

- [ ] **步骤 3：最小扩展现有脚本**

保留现有一次性 HOME、防止碰触已安装 Subtap、严格 audit/test、Doctor 与用户资料检查；新增：用 `brew tap-new subtap/acceptance` 创建不推送的隔离本地 Tap，A/B Formula 分别形成 local commit，在两个 commit 间切换完成 install/upgrade/rollback。第三方 local Tap 不需要关闭 Homebrew Formula API；禁止全局设置 `HOMEBREW_NO_INSTALL_FROM_API=1`，避免 fresh runner 因没有本地 core tap而无法解析核心依赖。核心依赖只安装一次，随后禁止自动更新/清理；每阶段比较 Python、NumPy、SciPy、GCC、OpenBLAS、FFmpeg 的版本、Formula revision 和 bottle digest；精确校验 A/B 版本、为全部哨兵保存 SHA256、逐命令保存 stdout/stderr/exit code并写出 `acceptance.json`。任何命令失败时先完成证据写入，再由 trap 返回原始非零状态。

- [ ] **步骤 4：验证并提交**

运行：`uv run pytest -q tests/test_release_safety.py`

预期：PASS。

```bash
git add scripts/homebrew_acceptance.sh tests/test_release_safety.py
git commit -m "test: 固化 Homebrew A-B-A 验收（任务 5/7）" -m "问题或需求描述：滚动 Homebrew 依赖会污染升级与回滚结论。" -m "修复或实现思路：同一 runner 固定依赖快照，精确校验版本并保存结构化失败证据。"
```

## 任务 6：增加候选 Formula 原型与依赖漂移 workflow

**文件：**
- 创建：`.github/workflows/homebrew-carrier.yml`
- 修改：`tests/test_release_safety.py`
- 修改：`scripts/check.sh`

- [ ] **步骤 1：编写失败测试**

```python
def test_homebrew_carrier_workflow_is_manual_or_scheduled_only() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/homebrew-carrier.yml").read_text())
    triggers = workflow["on"]
    assert set(triggers) == {"workflow_dispatch", "schedule"}
    assert "push" not in triggers
    assert all("timeout-minutes" in job for job in workflow["jobs"].values())


def test_homebrew_carrier_never_pushes_tap_or_creates_release() -> None:
    text = (ROOT / ".github/workflows/homebrew-carrier.yml").read_text()
    assert "git push" not in text
    assert "action-gh-release" not in text
    assert "contents: write" not in text
    assert "if: always()" in text


def test_scheduled_carrier_uses_reviewed_baseline_only() -> None:
    text = (ROOT / ".github/workflows/homebrew-carrier.yml").read_text()
    assert "packaging/homebrew/carrier-baseline.json" in text
    assert "git push" not in text
    assert "write-baseline" not in text


def test_carrier_baseline_identity_is_complete_when_present() -> None:
    path = ROOT / "packaging/homebrew/carrier-baseline.json"
    if not path.exists():
        pytest.skip("真实 A/B 尚未通过，baseline 按设计不存在")
    payload = json.loads(path.read_text())
    for side in ("previous", "candidate"):
        assert set(payload[side]) == {"tag", "version", "commit", "asset_url", "sha256"}
        assert all(payload[side].values())
```

- [ ] **步骤 2：确认测试失败**

运行：`uv run pytest -q tests/test_release_safety.py -k homebrew_carrier`

预期：FAIL，workflow 尚不存在。

- [ ] **步骤 3：实现只读原型 workflow**

`workflow_dispatch` 强制输入 `previous_tag`、`candidate_tag`、对应 peeled commits、版本和资产 SHA；先从 GitHub prerelease 下载两个版本化 wheelhouse，执行 `gh attestation verify --repo R-jed/Subtap`，拒绝同 tag/文件名不同 digest。随后渲染 A/B Formula，在不推送的隔离本地 Tap 中执行 `brew audit --strict --online`、A→B→A、`brew test`、import/动态库检查和最小本地模型 smoke。

scheduled 任务只读取仓库内人工审查提交的 `packaging/homebrew/carrier-baseline.json`，字段固定为 previous/candidate 各自的 tag、version、peeled commit、asset URL 和 SHA256；workflow 没有写回权限，也不能自动更新 baseline。首次真实 A/B 尚未通过时该文件不存在，scheduled job 必须上传 `status=blocked, reason=missing-reviewed-baseline` 后失败，不能显示监测通过。首次 A/B 成功后由人工核对 acceptance JSON 再单独提交 baseline，之后 schedule 才在全新 runner 检查最新 Homebrew 依赖。

所有 tag、commit、Formula local commit、URL、SHA、依赖快照、manifest、licenses、Formula、Doctor JSON 与 acceptance JSON 使用 `if: always()` 上传；不创建 tag、Release 或远端 Tap commit。

- [ ] **步骤 4：验证并提交**

运行：`uv run pytest -q tests/test_release_safety.py tests/test_homebrew_wheelhouse.py tests/test_homebrew_formula.py`

预期：PASS。

```bash
git add .github/workflows/homebrew-carrier.yml scripts/check.sh tests/test_release_safety.py
git commit -m "ci: 验证 Homebrew 候选载体（任务 6/7）" -m "问题或需求描述：当前方案缺少真实 Apple Silicon 原型和依赖漂移证据。" -m "修复或实现思路：新增只读手动与定时验收，不更新 Tap 或正式发布渠道。"
```

## 任务 7：运行本地原型门禁并更新候选状态

**文件：**
- 修改：`docs/adr/0001-homebrew-distribution-carrier.md`
- 修改：`docs/superpowers/specs/2026-07-13-homebrew-managed-scientific-stack-design.md`

- [ ] **步骤 1：执行完整静态门禁**

运行：`./scripts/check.sh`

预期：全部通过；失败时保留原始错误并停止，不更新 ADR 状态。

- [ ] **步骤 2：构建真实候选产物**

```bash
rm -rf dist/homebrew-wheelhouse
uv run python scripts/homebrew_wheelhouse.py build --python-version 3.13 --platform macosx_14_0_arm64 --output dist/homebrew-wheelhouse
uv run python scripts/render_homebrew_formula.py --wheelhouse dist/homebrew-wheelhouse --output dist/subtap.rb
```

预期：所有 SHA、许可证、禁止组件和 300 MiB 门禁通过；Formula 身份与 `pyproject.toml` 完全一致。

- [ ] **步骤 3：执行本机非破坏性验证**

运行 Formula 静态测试与临时 venv import/pip check。破坏性的 brew install/upgrade/rollback 只在一次性 CI runner 执行；当前工作机不得运行 `homebrew_acceptance.sh`。

- [ ] **步骤 4：更新文档并提交**

ADR 保持 `Proposed`，记录本地测试命令、commit、manifest SHA、体积和剩余真实 runner/RC A-B-A 证据。只有 workflow 真正成功后，另行提交将 ADR 改为 `Accepted`；本计划不发布 `brew install` 文案。

```bash
git add docs/adr/0001-homebrew-distribution-carrier.md docs/superpowers/specs/2026-07-13-homebrew-managed-scientific-stack-design.md
git commit -m "docs: 记录 Homebrew 候选验证结果（任务 7/7）" -m "问题或需求描述：载体状态必须只反映已经取得的真实证据。" -m "修复或实现思路：记录本地门禁结果并保留真实 CI 验收前的 Proposed 状态。"
```

## 最终验证

```bash
git status --short
./scripts/check.sh
graphify update .
```

要求：工作区干净；全量检查通过；知识图更新；代码审查无 Critical/Important；没有创建正式 tag、GitHub Release、PyPI 发布或 Tap 默认分支更新。
