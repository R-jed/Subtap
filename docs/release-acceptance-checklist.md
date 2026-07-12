# 发布验收清单

## 自动化门禁（CI 自动执行）

| # | 检查项 | 命令 | 通过标准 |
|---|--------|------|----------|
| 1 | 格式检查 | `black --check src tests` | 零 diff |
| 2 | 类型检查 | `mypy src/subtap` | 零 error |
| 3 | 全量测试 | `pytest -q` | 零 fail |
| 4 | 包内容检查 | `pytest tests/test_release_packaging.py` | 全部通过 |
| 5 | doctor --release | `subtap doctor --release --json` | `ok: true` |

## 本地验证（发布前手动执行）

| # | 检查项 | 命令 | 通过标准 |
|---|--------|------|----------|
| 6 | check.sh | `./scripts/check.sh` | 全部通过 |
| 7 | 冷安装 | `./scripts/cold_install_test.sh` | 全部 ✓ |
| 8 | 离线 pipeline | `./scripts/smoke_offline.sh` | SRT 交付检查通过 |
| 8a | Homebrew 验收 | `./scripts/homebrew_acceptance.sh` | 全部 ✓（需 tap 已配置） |

## 人工验收（真实设备）

| # | 检查项 | 步骤 | 预期结果 |
|---|--------|------|----------|
| 9 | 首次启动 | `brew install r-jed/tap/subtap && subtap` | 进入初始化向导 |
| 10 | 模型下载 | 向导中选择"高质量"，确认下载 | 下载完成，SHA256 校验通过 |
| 11 | 生成字幕 | 选择测试音频，选择"快速"，开始 | 字幕文件生成，内容合理 |
| 12 | 无网络模式 | 断网后运行 `subtap run --local-only` | 正常生成字幕 |
| 13 | 升级 | `brew upgrade subtap` | 程序更新，配置保留 |
| 14 | 卸载 | `brew uninstall subtap` | 程序删除，`~/.subtap` 保留 |
| 15 | 用户资料 | 检查 `~/.subtap` | 模型、热词、文稿、任务均在 |

## 发布前确认

- [ ] tag、Python 版本、GitHub Release、Homebrew Formula 版本一致
- [ ] SHA256SUMS 已生成并上传
- [ ] GitHub Release 包含构建来源证明
- [ ] Homebrew Tap 已自动更新
- [ ] `brew audit subtap` 通过
- [ ] Release notes 包含：用户可感知变化、迁移要求、已知限制
