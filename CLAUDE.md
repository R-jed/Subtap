## Git Commit Convention

Commits must use English, following Conventional Commits format:
```
<type>(<scope>): <description>

<body (optional)>
<footer (optional)>
```

### Types

| Type | 用途 |
|---|---|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 仅文档变更 |
| `style` | 代码风格（不影响逻辑） |
| `refactor` | 重构（不新增功能/修复 Bug） |
| `perf` | 性能优化 |
| `test` | 测试相关 |
| `build` | 构建系统/依赖变更 |
| `ci` | CI 配置 |
| `chore` | 其他杂项 |
| `revert` | 回滚 |
| `wip` | 进行中（慎用） |

### Rules

1. **description 首字母小写**，不以句号结尾
2. **description ≤ 72 字符**，超长内容放 body
3. **body 说明 what & why**，不说明 how（代码即 how）
4. **scope 可选**，用于标注影响范围（如 `parser`, `ui`, `api`）
5. **禁止引用其他项目名称**（如"借鉴 X"、"参照 Y"、"基于 Z"等）

### Good Examples

```
feat: add user authentication
fix(parser): handle empty input without crash
docs: update API reference for v2 endpoints
refactor(tui): extract state management into separate module
perf: cache parsed subtitle results to avoid re-computation
test: add edge case coverage for Unicode segmentation
chore: bump dependencies to latest stable versions
```

### Bad Examples

```
fix: Fixed stuff          # 首字母大写，以句号结尾
Feat: Add feature         # type 大小写错误
add new button            # 缺少 type 前缀
借鉴 Mole 项目优化代码    # 引用其他项目名称
```

## Test Materials

项目开发过程中的测试素材统一使用：`/Users/qunqing/Downloads/ASR-SRT测试音频` 文件夹内的文件

## 核心原则：复用策略（DRY原则）

- **优先复用**：如果 GitHub / npm 上有成熟的开源方案，**必须**直接复用，严禁自己重复造轮子（学习/实验除外）。
- **选型评估标准**（引入前必须执行）：
  - **热度与健康度**：优先 Stars > 1k（理想 >5k）；若为细分领域小众库，则重点看**近6个月是否有Commit**及Issue响应速度。
  - **兼容性扫描**：在 `import` 或修改 `package.json` 之前，必须检查该库的**License（禁止GPL类商业风险）**、**依赖版本（避免与现有框架冲突）**及**打包体积**。
- **互斥终止机制**：若检查发现方案与当前项目存在**架构冲突**（如强制要求升级底层JDK/Node版本）或**功能重叠**，**立即停止引入**，分析冲突根因，形成书面建议后提示用户，**严禁强行兼容**。

## Bug 修复原则（Fail-Fast 快速失败）

- **第一性原理**：分析 Bug 时，必须追溯数据流和底层逻辑的根源，禁止凭经验瞎猜或仅仅通过调整表面参数来“掩盖”问题。
- **严禁过早兜底**：针对**核心主流程**（如支付、登录、数据持久化），在未彻底修复根因之前，**严禁**编写 `try-catch` 空处理或返回默认假数据等兜底逻辑，以免掩盖错误真相。
- **例外豁免**：仅允许对**非核心辅助流程**（如本地缓存写入失败、埋点上报超时）进行降级处理，但必须打印完整的 Error 级别日志。

# Skills

本项目使用 https://github.com/mattpocock/skills 提供的技能框架（22 个 skills）。

Skills 位于 `~/.claude/skills/` 目录，每个 skill 有独立的 `SKILL.md` 文件。

当任务匹配某个 skill 时，使用 `Skill` 工具加载对应 skill 并严格遵循其流程。

## 核心规则

1. **收到任务时，先检查是否有匹配的 skill** — 哪怕只有 1% 的可能性也要检查
2. **不确定用哪个 skill 时，先调用 `ask-matt`** — 它是所有 skill 的入口路由器
3. **设计先于编码** — 收到功能需求时，先用 `grill-with-docs` 做需求对齐
4. **测试先于实现** — 写代码前先写测试（TDD）
5. **验证先于完成** — 声称完成前必须运行验证命令

## 主流程：idea → ship

大多数工作的路径：

1. **`grill-with-docs`** — 通过访谈打磨 idea。有 codebase 时从此开始，会保留学到的内容到 `CONTEXT.md` 和 ADR（无 codebase 用 `grill-me`）
2. **分支 — 问题能在对话中解决吗？**
   - 需要可运行答案（状态、业务逻辑、UI）→ 通过 `handoff` 切到 `prototype` 会话，再 `handoff` 回来
3. **分支 — 多会话构建？**
   - **Yes** → `to-spec` → `to-tickets`（声明阻塞关系）→ 逐 ticket `implement`
   - **No** → 直接 `implement`

`implement` 内部驱动 `tdd`（红-绿-重构），完成后运行 `code-review`（Standards + Spec 双轴）再提交。

### 上下文卫生

步骤 1-3 保持在同一上下文窗口，不要 compact。每个 `implement` 独立开新会话。接近 smart zone（~120k tokens）时用 `handoff` 切新会话。

## On-ramps（入口场景）

| 场景 | 入口 | 后续 |
|---|---|---|
| Bug/需求堆积 | `triage` | → `implement` |
| 某功能坏了 | `diagnosing-bugs` | → 修复 / → `improve-codebase-architecture` |
| 巨型模糊任务 | `wayfinder` | → `to-spec` → `to-tickets` → `implement` |

- **triage**: 仅处理**非自己创建**的 issue（bug 报告、外部需求）。`to-tickets` 产出的 ticket 已经是 agent-ready 的，不需要 triage
- **diagnosing-bugs**: 拒绝猜测，先建立 tight feedback loop（一条命令复现此 bug），再带回归测试修复
- **wayfinder**: 产出**决策 ticket 地图**，逐个解决直到路径清晰。完成后交给 `to-spec` 收敛为可构建计划

## 代码健康

- **`improve-codebase-architecture`** — 扫描发现可深化的模块，生成 HTML 报告。找到的候选模块可通过 `grill-with-docs` 进入主流程

## 底层词汇表（model-invoked）

- **`domain-modeling`** — 打磨项目领域语言：挑战模糊术语、解决一词多义、记录 ADR
- **`codebase-design`** — 深层模块设计词汇：module, interface, depth, seam, adapter, leverage, locality

## 跨会话

- **`handoff`** — 将对话压缩为 markdown 文件，新会话引用该文件继续。用于分叉（如 prototype）或上下文满时
- **`compact`**（内置） — 同一会话内压缩早期回合。阶段间断点使用，不要中途 compact

## Engineering — User-invoked（用户手动触发）

- **ask-matt**: 智能路由 — 根据场景推荐最合适的 skill 或工作流，是所有用户级 skill 的入口路由器
- **grill-with-docs**: 深度对齐访谈 + 领域建模 — 在需求对齐的同时构建项目领域模型，打磨术语并同步更新 CONTEXT.md 和 ADR
- **triage**: Issue 分诊 — 将外部 issue 按状态机流转，产出 agent-ready issues
- **improve-codebase-architecture**: 架构优化扫描 — 扫描发现可深化模块，生成 HTML 报告
- **setup-matt-pocock-skills**: 初始化配置 — 配置 issue 跟踪器、分诊标签、领域文档布局。每个仓库只需运行一次
- **to-spec**: 对话转 Spec — 将当前对话综合成规格说明发布到 issue 跟踪器
- **to-tickets**: 拆分为 Tickets — 将 spec 拆解为 tracer-bullet tickets，每个声明阻塞关系
- **implement**: 执行实现 — 按 spec/tickets 构建，驱动 TDD，完成后 code-review 再提交
- **wayfinder**: 大型任务路径规划 — 将超大工作拆分为决策 ticket 地图，逐个解决直到路径清晰

## Engineering — Model-invoked（模型自动或手动触发）

- **prototype**: 一次性原型 — 快速构建可运行原型回答设计问题（状态/逻辑/UI 验证）
- **diagnosing-bugs**: Bug 诊断循环 — 复现 → 最小化 → 假设 → 埋点 → 修复 → 回归测试
- **research**: 技术调研 — 后台 agent 调研问题，产出带引用的 Markdown 文件
- **tdd**: 测试驱动开发 — 红-绿-重构循环，逐个垂直切片构建
- **domain-modeling**: 领域建模 — 挑战术语、压力测试边界场景、同步 CONTEXT.md 和 ADR
- **codebase-design**: 代码库设计 — 小接口承载大量行为，放在干净接缝处
- **code-review**: 双轴代码审查 — Standards 轴 + Spec 轴并行运行
- **resolving-merge-conflicts**: 合并冲突解决 — 逐 hunk 按双方原始意图解决

## Productivity — User-invoked（用户手动触发）

- **grill-me**: 深度访谈 — 无 codebase 时的穷追不舍提问，不保留本地状态
- **handoff**: 会话交接 — 压缩对话为 markdown，新会话引用继续
- **teach**: 教学模式 — 跨会话教授技能，当前目录作为有状态工作区
- **writing-great-skills**: Skill 编写指南 — 编写和编辑 skill 的参考手册

## Productivity — Model-invoked（模型自动或手动触发）

- **grilling**: 访谈引擎（底层） — 由 grill-me 和 grill-with-docs 内部调用，一般不直接使用

## Agent skills

### Issue tracker

GitHub Issues（`R-jed/Subtap`）。See `docs/agents/issue-tracker.md`.

### Triage labels

5 个标准角色标签：`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`。See `docs/agents/triage-labels.md`.

### Domain docs

Single-context 布局：根目录 `CONTEXT.md` + `docs/adr/`。See `docs/agents/domain.md`.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
