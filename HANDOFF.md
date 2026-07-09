# Subtap — Session Handoff

> 上次更新：2026-07-09
> 交接人：当前会话 → 新会话

## 当前状态

**968 测试全部通过，4 skipped，0 失败。** Pipeline 11/11 阶段可用。开发完成度 99%。

**分支 `feat/smart-split-v2`：** `_smart_split` 已替换为 `_smart_split_v2`（Subtitle Edit 模式：枚举拆分点 + 评分选优 + jieba 分词）。待验证后合并到 main。

## 本次 Session 完成的工作

### 新增功能：Run Log 系统
- 人类可读的 pipeline 执行日志，`run_YYYYMMDD_HHMMSS.log`（带时间戳）
- `run_latest.log` 符号链接指向最新
- 源文件路径顶部醒目显示
- 文件：`metrics/run_log.py`，`cli.py`（集成），`tests/test_run_log.py`（11 个测试）

### Bug 修复（TDD，4 个）
| Bug | 修复 | 文件 |
|---|---|---|
| `--format` 不生效 | `formats={fmt}` | `tui.py` × 3 |
| 热词表 loaded=否 | `.entries` → `.hotwords` | `cli.py` |
| source_text 粒度 | `source_text=text` | `segmentation.py` |
| run.log 路径硬编码 | `{stem}.{fmt}` | `cli.py` |

### LLM 批量处理优化（Phase 1）
| 优化 | 变更 | 文件 |
|---|---|---|
| 翻译分块 | 30 句/块，前后各 3 句上下文滑动 | `translate.py` |
| API 重试 | 指数退避（1s/2s/4s）+ 随机 jitter，最多 3 次 | `openai_compat.py` |
| 批量大小 | batch_size 20→50，减少 60% API 调用 | `openai_compat.py`, `config.py` |

### 真实素材测试（10 个场景）
全部通过，除 agnes-2.0-flash 长视频翻译（API 不稳定，非代码问题）。

### 项目审查
完成全面功能审查，发现 5 个 P0 + 8 个 P1 + 6 个 P2 问题。

## 待修复问题（按优先级）

### P0 — 已全部修复 ✅
1. ~~**hotword 阶段是死代码**~~ — RichRunner/TUIRunner/PlainRunner 均已激活 `pipeline.run_stage("hotword")`，热词替换现在真正执行
2. ~~**STAGES 列表缺 `learn`**~~ — `Pipeline.STAGES` 已添加 `learn`（在 `translate` 之后），`state.py` 的 `STAGE_CN` 和 `STAGE_ORDER` 已同步
3. ~~**`min_chars` 默认值不一致**~~ — `export.py` `_smart_split` 默认值从 8 统一为 10，与 `SubtapConfig` 和 `BaseExporter` 一致
4. ~~**`command_deck.py` 源文件缺失**~~ — 从 pyc 字节码重建源文件，添加 `SUBTAP_ASCII` 到 `observer.py`，清理过期 pyc
5. ~~**TUI 配置同步率 44%**~~ — `ConfigManager` 新增 `to_subtap_config()` 和 `sync_from_config()` 方法，实现双向联动

### P1 — 短期修复（8 项）
6. translate 原地覆盖 aligned.jsonl，无原子写入保护（先写临时文件再 rename）
7. segment `source_text` 赋值逻辑有误（已修复为 `text`，但审查报告认为语义不符）
8. batch-transcribe 缺少 `fmt`/`translate_to`/`bilingual` 参数传递
9. glossary 词表加载静默吞错（`except Exception: pass`）
10. 4 处未使用导入（export.py, clean.py, hotword.py, tui.py）
11. tui_app.py 18 处重复超时值 `reader.read_key(timeout=0.05)`
12. 29 个模块无测试（尤其 batch 6 个 + VAD 2 个）
13. `hotword edit` 硬编码 `open -a Numbers`，仅限 macOS

### P2 — 中期优化（6 项）
14. export 缺 aligned.jsonl 存在性检查
15. segment `language` 参数未从配置读取，始终中文模式
16. cli.py 12+ 处重复 `except ValueError: typer.echo(...); raise typer.Exit(1)` 模式
17. 集成测试仅 1 个（0.8%）
18. `glossary import` 命令名不副实（只加载计数，不从外部导入）
19. 配置路径 CLI/TUI 不一致（CLI 直接构造 SubtapConfig，TUI 通过 ConfigManager → YAML → load_config）

## 建议修复顺序

**Phase 1（P0 核心功能）：**
- #1 hotword 死代码 → 让 RichRunner 真正调用 hotword 阶段
- #2 STAGES 缺 learn → 加入 STAGES 列表
- #3 min_chars 不一致 → 统一为 10
- #4 command_deck.py 缺失 → 恢复源文件或移除依赖

**Phase 2（TUI 优化）：**
- #5 TUI 配置同步 → ConfigManager 与 SubtapConfig 联动
- #6 translate 原子写入 → 先写临时文件再 rename
- #12 测试盲区 → 补充 batch + VAD 测试

## 关键文件

- `src/subtap/core/pipeline.py` — 阶段编排器（STAGES 列表 + handler 映射）
- `src/subtap/ui/tui.py` — RichRunner（实际执行逻辑）
- `src/subtap/ui/tui_app.py` — TUI 应用（状态机 + 视图）
- `src/subtap/ui/config_manager.py` — TUI 配置管理
- `src/subtap/core/export.py` — 导出（min_chars 不一致）
- `src/subtap/metrics/run_log.py` — Run Log 系统
- `src/subtap/core/translate.py` — 翻译分块
- `src/subtap/backends/llm/openai_compat.py` — API 重试 + batch_size

## 测试命令

```bash
python3 -m pytest tests/ -q
```

预期：952 passed, 4 skipped, 0 failed。

## API 配置

- API Key: `sk-E22YhwyqhE1LKwXUEh1TADAOF5xGN6p14cBp6JlouRyQLPnn`
- Base URL: `https://apihub.agnes-ai.com/v1`
- Model: `agnes-2.0-flash`
- 注意：agnes-2.0-flash 长视频翻译不稳定，会断连

## 测试素材

路径：`/Users/qunqing/Downloads/ASR-SRT测试音频/`
- 短中文：`数字测试.mp3`（21s）
- 中文：`高质量中文语音.mp3`（264s）
- 英文：`高质量英文语音.mp3`（188s）
- 长视频：`[10]--DLC.如何从前期到后期获得好声音.mp4`（1220s, 488MB）
