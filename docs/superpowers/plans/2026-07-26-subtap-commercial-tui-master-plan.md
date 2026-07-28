# Subtap 商业级 TUI 总体方案

日期：2026-07-26
状态：v2 核心预览版已实现，Stage 0–3 验收尚未完成
方案代号：Signal Desk

实现范围：独立 Home、新建字幕设置、Running / Completed / Failed /
Interrupted 任务视图、新版 Observer、共享原生文件选择器及 `subtap tui
--v2` 预览入口。现版 `subtap tui` 继续作为默认入口，人工验收通过前不切换。

## 1. 决策摘要

Subtap 采用并行重建策略：保留当前 TUI 可运行版本，另建一套 TUI v2。v2 不继承当前页面结构和 TCSS，只复用稳定的数据、任务、配置、文件选择与 Observer 边界。这样可以摆脱补丁式改造，也保留人工验收期间的可靠回退入口。

运行框架仍推荐 Python + Textual。当前问题不是 Textual 能力不足，而是现有 UI 生命周期、页面结构和产品呈现规则长期叠加，导致不同页面各自堆字段、画边框、选颜色，最终形成多个互不相干的工程面板。保留 Textual 是技术选型，不代表保留旧视觉结构。

最终方案由六部分组成：

1. 新建独立的 Textual TUI v2，现版只做维护和回退。
2. 严格的 P0/P1/P2 信息优先级。
3. 以终端字符单元为基础的响应式布局。
4. Running、Completed、Failed、Interrupted 使用不同页面结构。
5. CLI 与 TUI 使用同一套状态、错误和结果语言。
6. 自动回归测试通过后，必须再通过人工视觉验收。

保留：

- macOS 原生文件选择器。
- 现有 pipeline 语义。
- JSONL event log 与 reducer。
- Observer 独立进程边界。
- Textual Screen stack。
- `Esc` 返回、`Q` 退出或 detach、`X` 停止任务的交互合同。
- 现有 80 / 104 列水平断点。

现版与 v2 的关系：

- 现版冻结视觉功能，只修阻断使用的问题。
- v2 使用独立页面壳层、Theme、Screen、presentation components 和 snapshot 基线。
- pipeline、配置、glossary、文件选择、event log reducer 等非视觉能力优先复用。
- 不把旧 TCSS、旧页面布局或兼容分支复制到 v2。
- v2 通过完整验收前，不替换默认入口。
- v2 达标后切换默认入口，现版再经过一个稳定周期后删除。

停止：

- 零散修改现版 TCSS 来追赶 v2。
- 在正常页面使用大面积边框。
- 在首页使用占据五行以上的 ASCII Logo。
- 在运行页重复显示路径、进度、Chunk 和耗时。
- 将模型 ID、ASR 计数、隐私说明和原始日志放在第一视觉层。
- 暴露 Textual 默认 command palette 等框架界面。
- 用同一个页面骨架覆盖 Running、Completed 和 Failed。

## 2. 已确认事实与设计判断

### 2.1 已确认事实

- Subtap 当前使用 Python 和 Textual。
- 当前代码同时存在 legacy ANSI/TUI 视图、Command Deck、独立 Setup App 和独立 Observer App。
- “单一 Textual App”是目标方向，不是当前已经完成的事实。
- Observer 读取本地 JSONL event log，不应与模型推理和 pipeline 合并到同一进程。
- 当前运行页存在字段重复、动态内容权重不足、状态间结构雷同和大量无用途空白。
- Textual 已提供 Screen、ModalScreen、Grid、ProgressBar、RichLog、DataTable、Footer、Theme、响应式断点和 headless testing。

### 2.2 设计判断

- 迁移到 Bubble Tea 或 Ratatui 只会重写已有能力，不能自动解决信息层级问题。
- 引入 Vue TUI 会制造 Node/Vue 与 Python/Textual 两套运行时。
- TUI Studio 适合作为字符网格原型和视觉规范工具，不适合作为生产代码来源。
- 设计质量的第一约束应是信息预算，而不是颜色和边框。
- 任务状态页必须围绕“用户现在最需要知道什么、下一步能做什么”设计，而不是围绕内部对象字段设计。

## 3. 参考项目采用矩阵

| 来源 | 直接采用 | 转化后采用 | 明确拒绝 |
|---|---|---|---|
| Textual | Screen、ModalScreen、Grid、ProgressBar、RichLog、DataTable、Footer、Theme、breakpoints、测试能力 | 统一页面壳层与语义 token | 为每页另造基础控件 |
| TUI Studio | 无生产运行时代码 | 字符网格原型、组件层级、属性约束、主题对比、60/90/104 列预览 | React、Tailwind、Zustand、Vite、absolute positioning、gradient、导出代码直接进生产 |
| Vue TUI | 无生产运行时代码 | transcript viewport、stick-to-bottom、用户滚动后停止自动跟随、render-plane、host/capability boundary | Vue/Node renderer、experimental transcript/log 组件 |
| Bubble Tea | 无运行时依赖 | `state → update → view` 单向数据流 | Go 迁移、Bubbles/Lip Gloss 代码复制 |
| Ratatui | 无运行时依赖 | frame budget、stateful surface、只渲染当前 viewport | Rust 迁移、immediate-mode 重写 |

### 3.1 TUI Studio 的限定用途

只为以下五个页面建立原型：

- Home
- New Transcription
- Running
- Completed
- Failed

每个原型验证：

- 60、90、104 列。
- 24 和 56 行。
- true color、ANSI 16、NO_COLOR。
- 边框密度。
- 主动作是否唯一。
- CJK 与长路径是否自然换行或截断。

`.tui` 文件作为视觉规范保存。Textual exporter 只可生成一次性对照 scaffold，不可成为生产代码。

## 4. 产品呈现合同

### 4.1 信息优先级

P0：用户必须立即看到，否则无法判断状态或继续任务。

- 当前任务状态。
- 当前主要进度或最终结果。
- 当前阶段或关键错误。
- 当前主动作。
- Running 的最新字幕。
- Completed 的输出文件。

P1：支持理解和决策，但不应压过 P0。

- Pipeline 阶段导航。
- 输出目录。
- 关键任务配置摘要。
- 次要可用动作。
- 最近任务。

P2：工程详情，仅在 Details、Diagnostics 或折叠区域出现。

- 模型内部 ID。
- ASR draft count。
- alignment count。
- Chunk 编号。
- 完整路径。
- privacy 说明。
- 每阶段详细耗时。
- 原始事件和诊断日志。

### 4.2 五条默认约束

1. 正常页面原则上只有一个主进度条。
2. 同一字段不得在同一 viewport 原样出现两次。
3. 边框只在能明确改善分组时使用，不以“每页最多一个”机械限制设计。
4. 第一屏应有一个明确的 primary action；并列主任务确有必要时可在原型验收中例外。
5. engineering metric 默认不得进入 P0，Doctor 和 Diagnostics 等专业页面除外。

这些约束用于阻止页面重新变成工程面板，不是禁止设计探索。原型若能证明更好的层级和可读性，可以记录例外并采用。

### 4.3 空间预算

- Logo 不超过可视高度的 15%。
- 有有效内容时，不允许连续出现超过 8 行无用途空白。
- 120 列终端的内容最大宽度仍为 104。
- 90×56 Running 至少保留 12 行 live subtitle 空间。
- 页面不得出现嵌套的主滚动区。

## 5. 视觉系统

### 5.1 颜色

| Token | True color | ANSI 16 | NO_COLOR |
|---|---|---|---|
| background | `#0B0E11` | black/default | default |
| surface | `#11171C` | black | default |
| elevated | `#182027` | bright black | default |
| text | `#E6EBEF` | bright white | normal |
| muted | `#89949E` | bright black | normal |
| primary | `#63C5CF` | bright cyan | bold/underline |
| success | `#72C48B` | bright green | `[DONE]` |
| warning | `#D4AA60` | yellow | `[WARN]` |
| error | `#D76D74` | bright red | `[FAILED]` |

规则：

- 不设独立 link 色，链接使用 primary + underline。
- 颜色只增强语义，不独自承担语义。
- 每个状态必须同时有文字或字符标记。
- 不用渐变。
- 不用依赖两个相近背景色才能识别的层级。

### 5.2 强调层级

- Page title：bold，一行。
- Status tag：一行，`[RUNNING]`、`[DONE]`、`[FAILED]`、`[STOPPED]`。
- Section title：bold，正常文字色。
- Body：normal。
- Secondary：muted。
- 路径：正文或 primary + underline，只在可操作时强调。
- 代码、模型 ID、事件名：details 中使用，不形成第二套字体风格。

### 5.3 边框

- 页面外围不画框。
- 普通 section 默认无框，只用间距和标题分组。
- 分隔只用一行淡色 rule。
- bordered surface 仅用于：
  - Modal。
  - Critical error。
  - 当前唯一需要锁定注意力的结果区域。
- 不使用嵌套边框。
- 不混用圆角、方角、粗线、双线。

### 5.4 字符与图标

主字符集：

```text
[ ] pending
[>] active
[x] complete
[!] warning
[×] failed
```

ASCII fallback：

```text
[ ]
[>]
[x]
[!]
[X]
```

进度：

```text
████████░░░░
########....
```

不使用 emoji、Braille graph 或依赖特定 Nerd Font 的符号。

### 5.5 焦点

Focused control 至少同时使用两个信号：

- 前缀 `>`。
- reverse、underline 或明显 foreground emphasis 之一。

Hover 仅轻微变化。Disabled 必须同时降低强调并显示不可用原因。

## 6. TUI v2 系统边界与统一页面壳层

### 6.1 v2 系统边界

v2 新建自己的 UI composition root，负责：

- App lifecycle。
- Screen stack。
- Theme 和 capability detection。
- 页面壳层。
- 通用产品组件。
- task presentation 到 widget 的绑定。
- 全局 bindings 与 Footer。
- snapshot 和人工验收基线。

v2 不重新实现：

- pipeline。
- 配置读写。
- glossary 业务逻辑。
- 模型下载和检查逻辑。
- macOS 文件选择器。
- JSONL event log。
- Observer reducer。
- 输出文件生成。

旧 TUI 和 v2 可以暂时共同调用这些稳定接口，但不得互相 import 页面或 TCSS。

### 6.2 页面壳层

所有页面由四层组成：

1. Context line：页面名称、任务文件名或 breadcrumb。
2. Primary content：当前页面的唯一核心任务。
3. Notice region：只在有 warning、error 或完成提示时出现。
4. Contextual Footer：只显示当前状态可用操作。

Footer：

- 使用 Textual Footer。
- `compact=True`。
- `show_command_palette=False`。
- 不手写第二份快捷键说明。
- 不显示当前上下文不可用的 binding。

## 7. 响应式规则

### 7.1 水平断点

| 模式 | 宽度 | 规则 |
|---|---:|---|
| compact | `<80` | 单列；无 ASCII wordmark；History detail 进入独立页面 |
| regular | `80–103` | 任务页允许两列，约 32/68；表单可使用主区 + summary |
| wide | `>=104` | 内容宽度锁定 104；不增加第三栏；只增加 transcript 容量 |

### 7.2 垂直断点

| 模式 | 高度 | 规则 |
|---|---:|---|
| short | `<24` | 仅保留 P0；P1 进入折叠或滚动区 |
| standard | `24–39` | 完整核心流程；压缩说明文字 |
| tall | `>=40` | 增加 live content 与 history 行数，不增加 metadata |

任何尺寸都不能隐藏：

- 状态。
- Primary action。
- Critical error。
- Progress 或 result。

### 7.3 CJK 与路径

- 所有宽度计算使用项目已有 display-width helper。
- 禁止使用 Python `len()` 或人工补空格做视觉对齐。
- 文件名优先保留尾部扩展名。
- 路径在 overview 中显示缩略形式，完整路径进入 Details。
- 正文由 widget 自身换行，不在 presentation string 中硬换行。

## 8. 页面蓝图

### 8.1 Home

目标：选择工作，而不是展示品牌。

```text
SUBTAP
Local offline subtitles

> New transcription
  Batch
  Observe / History

  Models
  Glossary
  Setup
  Doctor
```

规则：

- Wide 最多使用 2–3 行固定实体字 wordmark，并确保准确显示 `SUBTAP`。
- Regular/compact 只显示普通文字 `SUBTAP`。
- New transcription 是唯一 primary action。
- 有历史任务时最多显示 3 条 recent tasks；无历史时整个区域消失。
- 版本与 repository 信息移到 Doctor/About。

### 8.2 New Transcription

目标：在同一页面选择媒体并设置任务。

Regular：

```text
New transcription

Media
[ interview.mov                                  ] [Choose]

Task settings                         Summary
Model          High quality           interview.mov
Language       Auto                   → interview.srt
Glossary       Default                High quality
Manuscript     None
Output         Downloads
Subtitle size  25

                                      [Review task]
```

规则：

- 文件选择必须在页面内。
- 选择错误文件后可直接重新选择。
- Summary 只显示 3–5 个真正决定输出的值。
- 默认项解释、内部模型 ID、privacy 长文不在主表单出现。
- 同类多选操作保持同一行、同高、同宽规则。
- Compact 顺序堆叠，Summary 放在字段之后。

### 8.3 Review

目标：在开始高成本任务前确认输入与结果位置。

```text
Review transcription

interview.mov
Model       High quality
Language    Auto
Glossary    Default
Output      interview.srt

[Back]                              [Start transcription]
```

规则：

- 使用 ModalScreen。
- Start transcription 是唯一 primary action。
- 只显示非默认或决定结果的设置。
- Back 返回 New Transcription 并保留输入。

### 8.4 Running

目标：知道任务正在工作、进行到哪里、最近识别了什么。

Regular/Wide：

```text
interview.mov                                      [RUNNING]
Speech recognition · 22% · 00:06
███████░░░░░░░░░░░░░░░░░░░░

Pipeline                       Live subtitles
[x] Audio normalization       所以，假如你现在要买 GR4……
[x] Audio segmentation        对于部分人来说，构图会有点挑战。
[>] Speech recognition
[ ] Text cleanup
[ ] Subtitle segmentation
[ ] Alignment
[ ] Glossary
[ ] Export

Output  ~/Downloads/interview.srt
```

规则：

- 进度条全宽且只出现一次。
- 顶部只显示文件名、状态、当前阶段、百分比和耗时。
- 32/68 两列，live subtitles 是最大动态区域。
- transcript 默认 stick-to-bottom；用户向上滚动后停止自动跟随，回到底部后恢复。
- Pipeline 是导航，不是九个独立卡片。
- model、Chunk、ASR counts、隐私说明、完整路径进入 Details。
- `X` 只在 Running 存在，并打开危险确认。

Compact：

```text
interview.mov  [RUNNING]
22% · Speech recognition · 00:06
███████░░░░░░░░░░░

Stage 3/8  Speech recognition

Live subtitles
……
```

### 8.5 Completed

目标：立即获得结果并继续下一步。

```text
interview.mov                                        [DONE]
Subtitle created in 00:50

Output
~/Downloads/interview.srt

> Open subtitle
  Open folder
  New transcription

Details
8 stages completed · 39 subtitles
```

规则：

- 不显示 100% progress bar。
- 输出文件和动作成为视觉主体。
- Pipeline 默认折叠成一句结果。
- 不继续使用 Running 的面板骨架。
- TUI、CLI 和 History detail 使用完全相同的结果术语。

### 8.6 Failed

目标：理解失败原因并采取下一步。

```text
interview.mov                                      [FAILED]
Unable to write subtitle file

The output directory is not writable.

> Choose another output directory
  Retry
  Open diagnostics
```

规则：

- 第一屏只显示用户可理解的错误、原因和 next action。
- traceback 和 raw event 仅在 diagnostics。
- Retry 表示从头重试。
- 没有可验证 checkpoint 能力时，禁止显示 Resume。

### 8.7 Interrupted

与 Failed 分开：

```text
interview.mov                                     [STOPPED]
Task stopped by user

No subtitle file was created.
Temporary files were preserved for diagnostics.

> New transcription
  Open diagnostics
```

必须明确说明：

- 谁停止了任务。
- 已生成什么。
- 保留了什么。
- 下一步可做什么。

### 8.8 Observe / History

Regular/Wide：

- 左侧 task list。
- 右侧复用统一 task detail presentation。
- 正在运行任务显示 live state。
- 完成、失败、停止使用对应的状态专属 detail。

Compact：

- 先显示 task list。
- Enter push 到独立 detail screen。
- Esc 返回 task list。

不得为 History 重新定义一套字段。

### 8.9 Batch

- 顶部一个 overall progress。
- 每个任务一行 compact state。
- 不为每个任务画大型 progress bar。
- 当前选中任务可以进入统一 task detail。
- 完成后总结成功、失败、停止数量和输出目录。

### 8.10 Models

- 以 Ready、Missing、Downloading、Failed 为核心状态。
- 每个模型一行，详细版本和路径进入 detail。
- Missing 的 primary action 是 Download。
- 不用颜色区分唯一状态。

### 8.11 Glossary

三个核心任务：

- Edit default glossary。
- View learned glossary。
- Choose another glossary。

Regular 下三个动作同一行、同高、使用统一宽度规则。
Compact 下顺序堆叠。

说明：

- `default.txt` 由用户维护。
- `learned.txt` 由系统维护，可能覆盖手动修改。
- 不在主页面显示格式教程；首次编辑或 Help 中说明“一行一个热词”。

### 8.12 Setup

- 明确标注“默认设置”，避免与单次任务设置混淆。
- 表单按 Model、Processing、Output、Advanced 分组。
- 当前有效值在右侧 summary 中显示。
- 保存成功给短暂 notice，不增加完成页。
- 危险或不可逆更改使用 ModalScreen。

### 8.13 Doctor

- 首屏优先显示 Failed、Warning、Passed 数量。
- 失败项包含 problem、cause、next action。
- raw command output 默认折叠。
- About、版本和 repository 信息放在此处。

### 8.14 Empty、Loading 与 Modal

- Empty state 必须说明“为什么为空”和“下一步做什么”。
- Loading 只在实际等待时显示 spinner，不模拟进度。
- Modal 只用于确认、阻断错误和短决策，不承载完整页面。
- 非阻断通知使用 notice region，不弹 Modal。

## 9. 导航与输入合同

固定键位：

```text
Esc        关闭当前 layer / 返回上一级
Q          退出 UI；Observer 中 detach
X          停止 Running task，并确认
Enter      执行当前焦点动作
Tab        下一个交互控件
Shift+Tab  上一个交互控件
```

规则：

- Back 永远返回上一级，不退出工具。
- Quit 永远退出工具；Observer 中只退出观察，不停止任务。
- 停止任务与退出观察必须是不同动作。
- Mouse 只映射已有键盘动作，不产生键盘无法完成的功能。
- 所有页面必须存在完整键盘路径。

## 10. CLI 用户体验合同

### 10.1 输出层级

默认：

- 当前阶段发生变化时输出一行。
- 完成时输出结果、文件和目录。
- 错误时输出 problem、cause、next action。

Verbose：

- 增加模型、Chunk、详细计时和诊断事件。

Debug：

- 才输出 traceback 和 raw event。

### 10.2 Non-TTY

- 不输出 cursor controls。
- 不输出 spinner escape sequence。
- 只输出 stage transition 和最终结果。
- 遵守 NO_COLOR。

### 10.3 Cancellation

- 前台转录第一次 `Ctrl+C` 请求 graceful interruption。
- 第二次 `Ctrl+C` 才允许 force terminate。
- Observer 的 `Q` 或 `Ctrl+C` 只 detach。
- 停止真实任务必须使用明确 stop command 或 TUI `X` confirmation。

### 10.4 术语

- `Retry`：从头重新执行。
- `Resume`：仅在存在经过验证的 checkpoint 时使用。
- `Open subtitle`：打开结果文件。
- `Open folder`：打开结果所在目录。
- `Diagnostics`：用户主动进入的工程详情。

## 11. 状态与数据边界

统一数据流：

```text
pipeline events
    ↓
JSONL reducer
    ↓
TaskPresentation
    ↓
Textual widgets / CLI renderer / History detail
```

约束：

- Widget 不读取 pipeline 内部对象。
- Presentation 不执行副作用。
- Running、Completed、Failed、Interrupted 使用同一状态模型，不使用同一视觉骨架。
- Overview 只消费 P0/P1。
- Details 消费 P2。
- History 和 Observer 不重新解释事件。
- 解析错误按 fail-fast 原则暴露，不生成假状态。

## 12. 实施阶段与停止条件

### Stage 0：冻结设计资产

产物：

- P0/P1/P2 priority matrix。
- visual token 表。
- Home、New、Running、Completed、Failed 的 TUI Studio 原型。
- 60/90/104 × 24/56 验收截图。

GO：

- 五个页面通过人工视觉确认。
- 所有状态在 NO_COLOR 可辨认。

STOP：

- 仍依赖边框或颜色解释层级。
- 仍在原型阶段持续改 TCSS。

### Stage 1：建立独立 TUI v2 骨架

目标：

- 新建 v2 composition root，不修改旧页面结构。
- 一个 canonical Textual Theme。
- 一个统一页面壳层。
- Footer 由当前 bindings 自动生成。
- 禁用默认 command palette chrome。
- 提供明确的 preview 入口，默认入口仍指向现版。

GO：

- v2 Home、空页面、Modal 和 Footer 使用同一视觉语言。
- 启动 v2 不影响现版启动。

STOP：

- v2 页面继续各自定义颜色或 footer。
- 为复用旧页面而把旧 TCSS 引入 v2。

### Stage 2：统一 TaskPresentation

目标：

- 明确 P0/P1/P2 字段。
- 消除重复进度、路径、耗时和 Chunk。
- CLI、Observer、History 共用状态与结果词汇。

GO：

- 一个 reducer 输入可生成 Running、Completed、Failed、Interrupted 的稳定 presentation。

STOP：

- Widget 仍拼接业务状态或访问 pipeline 内部对象。

### Stage 3：核心任务页面

顺序：

1. Running。
2. Completed。
3. Failed / Interrupted。
4. Review。
5. New Transcription。

GO：

- 页面结构随状态改变，不只是颜色改变。
- 90×56 Running 至少 12 行 transcript。

### Stage 4：导航与二级页面

范围：

- Home。
- Models。
- Glossary。
- Setup。
- Doctor。

GO：

- Esc、Back、Q、X 合同在所有页面一致。
- Compact 无横向滚动。
- v2 内部所有页面使用同一 App lifecycle；不再通过退出 App 模拟页面跳转。

### Stage 5：History、Observe 与 Batch

目标：

- 所有 task detail 复用统一 grammar。
- Batch 只有一个 overall progress。
- Observer 独立进程边界不变。

GO：

- live task 与 historical task 不产生第二套字段定义。

### Stage 6：CLI 与能力降级

范围：

- TTY / non-TTY。
- true color / ANSI 16 / NO_COLOR。
- Unicode / ASCII fallback。
- short-height。

GO：

- 重定向到文件后无终端控制符。
- NO_COLOR 不损失状态语义。

### Stage 7：删除旧视觉系统

仅在 v2 完整通过、切换默认入口并经过稳定周期后删除：

- legacy CSS。
- 重复 Rich colors。
- 手写 footer text。
- 旧 observer panes。
- 旧 ASCII banner。
- 已无调用的 legacy ANSI 页面。

人工验收失败即 STOP，不能用 snapshot 通过代替。

### Stage 8：切换与回退

切换条件：

- v2 全部阻断验收项通过。
- 使用项目真实测试音频完成 Transcribe、Observe、Completed、Failed 和停止任务流程。
- 旧版与 v2 输出结果一致。
- v2 未改变公开 CLI 参数和配置格式。

切换方式：

- v2 成为默认 `subtap tui`。
- 旧版保留一个明确的临时 legacy 入口。
- 稳定周期内记录 v2 启动、页面异常和任务操作日志。
- 出现阻断问题时只回退入口，不回退 pipeline 或用户数据。

删除旧版前必须再次人工确认，不能因 v2 已设为默认就自动删除。

## 13. 验收矩阵

每个 Primary screen：

- 60×56。
- 90×56。
- 120×56。

关键流程额外：

- 60×24。
- 90×24。

| 页面/状态 | 阻断验收条件 |
|---|---|
| Home | Logo ≤15% viewport；New transcription 是第一主动作；无大面积空白 |
| New | 媒体、核心设置、Review 可完成；60 列无横向滚动 |
| Review | 输入、输出、关键设置和 Start 第一屏可见 |
| Running | 一个主 progress；subtitle 是最大动态区域；无重复路径或进度 |
| Completed | progress 消失；output/action 成为视觉主体 |
| Failed | error + next action 第一屏可见；traceback 不可见 |
| Interrupted | 与 Failed 明显不同；保留文件情况明确 |
| History | 60 列 master/detail 分层；wide 可 master/detail |
| Batch | 一个 overall progress；任务只显示 compact state |
| Models | Ready/Missing 在无颜色时可辨认 |
| Glossary | 三个核心任务在 regular 下对齐 |
| Setup | defaults 与 per-task settings 不混淆 |
| Doctor | failure/warning 优先；raw output 默认隐藏 |

全局阻断项：

- 60 列零 horizontal scrolling。
- 正常页面无 nested primary scroll region。
- 120 列内容宽度不超过 104。
- 90×56 Running 至少 12 行 live content。
- 有有效内容时无连续 8 行以上无用途空白。
- NO_COLOR 下 Running、Done、Failed、Stopped 可辨认。
- ANSI 16 下不依赖近似背景色区分区域。
- NO_COLOR 下焦点仍可见。
- 关闭 mouse 后可完成全部工作流。
- CJK、英文长词、emoji 文件名和长路径均不破坏布局。

## 14. 自动验证与人工验收的分工

自动验证：

- Screen stack 与 Back/Q/X 行为。
- 指定 terminal size 的 headless tests。
- presentation snapshot。
- NO_COLOR snapshot。
- ASCII fallback。
- 长路径和 CJK display width。
- Running/Completed/Failed/Interrupted 状态转换。
- non-TTY 输出无 escape sequence。

人工验收：

- 信息层级是否自然。
- 焦点移动是否容易理解。
- 颜色是否舒适但不过度。
- 运行时字幕是否稳定、不跳动。
- 终端实际字体下的 CJK 宽度。
- 60/90/120 列下是否像同一个产品。
- Running、Completed、Failed 是否一眼可区分。

## 15. 明确不做

- 不迁移到 Go、Rust、Vue 或 Node。
- 默认不引入第二种生产 TUI runtime；若独立原型证明 Textual 无法达到必要交互，再重新进行框架、许可证、打包体积和迁移成本评估。
- 不复制 experimental 组件。
- 不增加插件式主题系统；先只交付一个产品主题。
- 不增加 dashboard 图表。
- 不增加动画框架。
- 不承诺 Resume。
- 不为了 wide terminal 增加第三栏。
- 不在 v2 实现期间继续零散调整现版视觉。

## 16. 设计交付物

进入实现前必须具备：

1. 本方案文档。
2. 参考项目研究报告。
3. Subtap 当前架构评审报告。
4. GPT-5.6 Sol 设计审查记录。
5. 五个 TUI Studio 原型。
6. token 与 P0/P1/P2 表。
7. 页面与状态验收矩阵。
8. 人工验收指令。

## 17. 第一方资料

- [TUI Studio](https://github.com/jalonsogo/tui-studio)
- [Vue TUI](https://github.com/Simon-He95/vue-tui)
- [Bubble Tea](https://github.com/charmbracelet/bubbletea)
- [Textual](https://github.com/Textualize/textual)
- [Textual Screens](https://textual.textualize.io/guide/screens/)
- [Textual Layout](https://textual.textualize.io/guide/layout/)
- [Textual Styles](https://textual.textualize.io/guide/styles/)
- [Textual Input](https://textual.textualize.io/guide/input/)
- [Ratatui](https://github.com/ratatui/ratatui)
- [Ratatui application patterns](https://ratatui.rs/concepts/application-patterns/)

## 18. 最终判定

推荐方案是：

> Textual native runtime + strict task presentation contract + cell-first responsive layout + progressive disclosure + capability degradation + manual visual release gate.

实施的第一个动作不是修改现版首页或运行页，而是冻结 Signal Desk 的 token、五个核心原型和 P0/P1/P2 presentation matrix，然后建立独立 TUI v2 骨架。v2 可以大胆重构页面和交互，但不能重新实现稳定业务能力，也不能在通过验收前替换现版入口。
