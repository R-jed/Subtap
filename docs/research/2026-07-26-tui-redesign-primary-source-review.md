# Subtap TUI 重设计：一手资料调研与架构建议

日期：2026-07-26
范围：首页品牌区、单次转录设置、多控件布局、视觉层级、返回/退出语义、Textual 架构取舍。

## 结论

1. **保留 Textual，不更换 TUI 框架。** Textual 已经原生提供屏幕栈、响应式断点、Grid/Horizontal、主题变量、按键绑定与可测试的交互模型；Subtap 当前问题不是框架能力不足，而是 Screen 化只完成了一半，尚未形成覆盖首页、设置页和任务页的共享 UI system。
2. **保留现有 `CommandDeckApp` Screen stack，升级而不是另建平行导航层。** `RunSetupScreen` 和二级 `CommandPage` 已经进入主 App；应把 `CommandPage` 提升为共享页面骨架，再让 Home、Run Setup 和 Observer 逐步复用。Observer 继续保持独立 App 和日志恢复边界，不为视觉统一改变进程模型。
3. **首页品牌区采用响应式“双形态”。** 宽终端显示经过人工校验的固定 ASCII wordmark；窄终端退化为普通粗体 `SUBTAP`。说明、版本和项目地址置于 logo 下方，不再与 logo 并排。不要运行时生成 ASCII，也不要新增 logo 依赖。
4. **单次转录把文件选择并入设置页。** 页面先出现，首行是“媒体文件”选择控件；点击后继续复用现有 macOS 原生选择器。用户取消选择器时仍停留在当前设置页，选错后可重新选择，Esc 返回首页。
5. **同类操作放在同一行，以 Grid 保证尺寸一致。** 热词表的“编辑默认 / 查看学习结果 / 选择其他”应为一行三列；窄终端通过 Textual 断点自动变成一列，而不是硬挤或截断。
6. **取消顶部框标题，保留清楚但克制的层级。** 页面标题改为内容区内的一行标题；主要层级由背景面、间距、字重和一个主色构成。边框仅用于错误确认、危险操作或需要隔离的弹窗。
7. **导航语义固定为：Esc = Back/Cancel，Q = Quit。** 在弹窗中 Esc 先关闭弹窗；在二级页 Esc 返回上一页；首页 Esc 不退出。`q`（以及可选的 `Ctrl+C`）在任何页面直接退出整个工具。

## 当前实现的根因

### 1. 主交互已经 Screen 化，但共享页面系统停在半途

当前 `CommandDeckApp` 已经把 Transcribe、Batch、Observe、Models、Glossary 和 Doctor 放入同一 Screen stack；Run Setup 与多个二级页面可以返回首页。

真正的割裂发生在表现层：Home 自己定义品牌、菜单和底部提示，`_RunSetupForm` 自己维护表单布局与动作区，`CommandPage` 只提供初级模板，Observer 又维护另一套 task panel、details 和 keys。它们共享导航机制，但不共享完整的信息层级、间距、响应式规则、Footer 和任务状态表达。

### 2. 文件选择已进入设置页，但设置页仍是独立视觉语法

当前主路径已经是 `CommandDeckApp -> RunSetupScreen`，媒体文件选择位于设置页内，取消选择不会丢失页面状态。

剩余问题不是流程，而是 `_RunSetupForm` 仍拥有独立的 section、hint、status、footer-actions 和大面积全宽控件。`RunSetupApp` 目前是兼容和测试入口，不能在没有检查 direct invocation、CLI 入口和 imports 前直接删除。

### 3. 二级页已有 `CommandPage`，但复用深度不足

`CommandPage` 已统一 Esc 返回、Q 退出、基础颜色以及标题、说明、状态、动作的基本节奏；准确问题不是“完全没有共享页面层”，而是它仍停留在浅模板，尚未覆盖 Home、Run Setup 和任务工作区。

复杂表单继续使用 Textual `Grid`、`Horizontal` 和现有 widgets，不新增 Card、Metric、ButtonRow 等一次性组件。

### 4. Observer 的独立边界正确，视觉与状态语言不统一

正确数据方向必须保持：

```text
pipeline -> run.log.jsonl -> observer
```

不能改成 pipeline 通过进程内 EventBus 直接驱动 Observer。`EventBridge` 的 live push 与 Observer reducer 的 replay/recovery 生命周期不同。

Observer 当前最大问题是信息层级：任务状态、阶段、进度、Chunk、模型、计数、隐私和输出同时占据首屏，随后又重复显示进度、阶段、当前工作、字幕和输出。数据并不缺，缺的是统一的 task presentation。

## 一手资料与成熟模式

### Textual：屏幕栈就是多页面产品的原生模型

Textual 官方文档把 Screen 定义为占满终端的页面，并明确维护一个 screen stack：`push_screen()` 进入新页，`pop_screen()` 回到前一页，`dismiss(result)` 关闭当前页并把结果交给调用者。文档示例也直接将 Esc 绑定为 `pop_screen`。[Textual Screens](https://textual.textualize.io/guide/screens/)

这与 Subtap 的产品语义完全一致：

```text
HomeScreen
  ├─ TranscribeScreen
  │    └─ Confirm/RunningScreen
  ├─ BatchScreen
  ├─ ObserveScreen
  ├─ ModelsScreen
  ├─ GlossaryScreen
  ├─ SetupScreen
  └─ DoctorScreen
```

返回只删除栈顶页面；退出结束整个 App。无需自行维护历史栈。

### Textual：响应式布局、同行对齐与窄终端降级都是原生能力

Textual 官方布局指南提供 `Horizontal`、`Vertical` 和 `Grid`。`1fr` 可让同一行控件平均分配宽度；Grid 支持列宽、行高、间距和跨列，官方也提醒复杂表单不要靠多层 Horizontal/Vertical 人工拼接。[Textual Layout](https://textual.textualize.io/guide/layout/)

Textual 还提供 `HORIZONTAL_BREAKPOINTS`：终端宽度变化时自动给 Screen 增加 CSS class，再由 TCSS 切换 Grid 列数。官方示例在 0、40、80、120 列四个断点上切换 1/2/4/6 列。[官方 breakpoints 示例](https://github.com/Textualize/textual/blob/06dbeef4bb70fb718236aa418ed658ef4667a126/examples/breakpoints.py#L14-L49)；[App API](https://textual.textualize.io/api/app/#textual.app.App.HORIZONTAL_BREAKPOINTS)

Subtap 可采用更少的两个断点：

| 终端宽度 | 热词操作区 | 表单内容宽度 | 首页 logo |
|---|---|---|---|
| `< 80` | 1 列 | 全宽、保留左右 1 格 | 普通 `SUBTAP` |
| `>= 80` | 3 列等宽 | 最大约 88 格、居中 | 固定 ASCII wordmark |

### Textual：主题变量比散落的十六进制颜色更稳

Textual Theme 提供 `$background`、`$surface`、`$panel`、`$primary`、`$accent`、`$foreground`、`$text-muted`、`$success`、`$warning`、`$error` 等语义变量，并自动生成可读的前景色和明暗层级。[Textual Themes](https://textual.textualize.io/guide/design/)

成熟的 Textual 应用 Posting 也采用同样的结构：普通文字品牌头、主体区、紧凑 Footer；背景、焦点、状态和滚动条均从主题变量派生，而不是每个页面各写一套颜色。Posting 还用 class 在横向/纵向主体布局之间切换。[Posting `AppHeader` / `AppBody`](https://github.com/darrenburns/posting/blob/56703a11513e8e74e681b4f859f31945b71e746f/src/posting/app.py#L93-L109)；[Posting 布局切换](https://github.com/darrenburns/posting/blob/56703a11513e8e74e681b4f859f31945b71e746f/src/posting/app.py#L752-L757)；[Posting 主题化样式](https://github.com/darrenburns/posting/blob/56703a11513e8e74e681b4f859f31945b71e746f/src/posting/posting.scss#L212-L304)

### K9s 与 lazygit：Back 和 Quit 必须是两个动作

K9s 的官方按键表明确区分：

- `Esc`：回到上一个 view / 退出当前 view 或输入模式；
- `:quit`、`:q`、`Ctrl+C`：退出 K9s。

来源：[K9s 官方 README](https://github.com/derailed/k9s/blob/436ea2e9f23c5dd2d8e05c3e974220657524ef17/README.md#L385-L396)

lazygit 采用同一语义：全局 `Esc` 是 Cancel，`q` / `Ctrl+C` 是 Quit；在二级区域中 Esc 明确为 “Exit back to side panel”。[lazygit 官方按键表](https://github.com/jesseduffield/lazygit/blob/292035709f880f33b9f9c90177f1d2fe63f2bd6a/docs/keybindings/Keybindings_en.md#L20-L31)；[二级区域返回](https://github.com/jesseduffield/lazygit/blob/292035709f880f33b9f9c90177f1d2fe63f2bd6a/docs/keybindings/Keybindings_en.md#L220-L228)

这不是偏好差异，而是成熟终端工具普遍使用的防误退语义。

### 品牌区：可读性优先，装饰只在宽终端出现

Posting 使用普通粗体产品名和可选版本号构成紧凑 header，不依赖大字符图案。[Posting header](https://github.com/darrenburns/posting/blob/56703a11513e8e74e681b4f859f31945b71e746f/src/posting/app.py#L93-L105)

K9s 若显示 ASCII logo，则将其封装为独立 Logo 组件，给 logo 固定 6 行、状态固定 1 行，并由 skin 控制颜色，而不是运行时按终端字体生成。[K9s Logo](https://github.com/derailed/k9s/blob/436ea2e9f23c5dd2d8e05c3e974220657524ef17/internal/ui/logo.go#L15-L40)

由此得到适合 Subtap 的组合：

- `SUBTAP` 必须有普通文本版本，作为不会误读的主名称；
- ASCII 版本只是宽屏装饰，必须是仓库内固定文字并有渲染快照；
- 描述、版本、项目地址在 logo 下方组成第二层，不与图案横向竞争；
- 不引入 `pyfiglet` 或运行时字体生成。终端字宽和字体差异会让生成结果不可控，新增依赖也没有产品收益。

## 逐项设计建议

### 1. 首页品牌区

推荐结构：

```text
<宽屏固定 ASCII SUBTAP / 窄屏普通粗体 SUBTAP>
本地离线字幕生成
v0.1.0rc6  ·  github.com/R-jed/Subtap

Transcribe   单个音频或视频生成字幕
Batch        批量转录多个媒体文件
...
```

具体约束：

- 品牌区与菜单左边缘一致；
- logo、说明、版本之间只保留一行节奏，不做并排双栏；
- 菜单描述从固定列开始，避免中英文长度导致锯齿；
- 选中态使用一处 accent：左侧指示条或文字颜色二选一，不同时加背景、粗体、箭头三种强调；
- 首页不显示边框或顶栏标题。

### 2. 单次转录页内选择文件

推荐第一组字段：

```text
媒体文件
[ 未选择 /Users/.../video.mp4                         ] [选择…]
```

行为：

1. 进入 TranscribeScreen 时不弹文件窗口。
2. 用户点击“选择…”才调用现有 `_choose_native_file()`。
3. 选择成功后更新路径字段和简短文件信息。
4. 取消 macOS 对话框不改变当前值、不退出页面。
5. 路径为空时“检查设置/开始”不可用，并在本页给出明确提示。
6. Esc 返回首页；Q 退出整个工具。

Textual 自带 `DirectoryTree`，可在终端内接收 `FileSelected` 事件，也支持过滤路径。[Textual DirectoryTree](https://textual.textualize.io/widgets/directory_tree/) 但 Subtap 仅发布 Apple Silicon macOS，且仓库已有可区分“用户取消”和“选择器失败”的原生 picker，因此**推荐保留 macOS picker，只把触发入口移入页面**。只有未来需要纯 SSH/无图形环境时，才增加 DirectoryTree 作为另一种输入方式。

### 3. 多选项同行与对齐

热词区推荐：

```text
热词表
[ 使用默认热词表                                      ▼ ]
[编辑默认热词表] [查看学习结果] [选择其他热词表]
default.txt 由你维护；learned.txt 由系统更新。
```

规则：

- 三个按钮属于同一个 Grid row，`grid-columns: 1fr 1fr 1fr`；
- 同一行按钮高度固定一致，文字居中；
- 行间距 1、列间距 1；不要用每个 Button 各自的 margin 修对齐；
- 帮助文本占整行并使用 `$text-muted`；
- 窄终端把同一 Grid 改为 1 列，不截断按钮文字；
- “参考文稿”“输出目录”同样使用“路径/Select + 选择按钮”的字段行。

### 4. 去掉顶部框标题后的视觉层级

Textual 的 `border_title` 默认空字符串即不显示；它只在 widget 有 border 时出现。[Textual Widgets：Border titles](https://textual.textualize.io/guide/widgets/#border-titles)

建议采用四层视觉系统：

| 层级 | 用途 | 建议 |
|---|---|---|
| Background | 页面留白 | `$background` |
| Surface | 表单内容区 | `$surface` 或透明，不加边框 |
| Panel | 需要分组的资源/状态块 | `$panel`，少量使用 |
| Accent / semantic | 焦点、主按钮、成功/警告/错误 | `$primary`、`$accent`、`$success`、`$warning`、`$error` |

页面标题使用内容区内的粗体 `Static`；次要说明用 `$text-muted`；主按钮只保留一个 `variant="primary"`。圆角边框仅用于 Modal、危险确认和严重错误，不给每个表单区都套框。

推荐统一使用一个主题，不再让首页、首次启动、设置页和 Observer 分别维护 `#0b0d10`、`#000000`、`#111820` 等近似但不一致的颜色。

### 5. Back 与 Quit

统一契约：

| 输入 | 首页 | 二级页 | Modal / 展开态 |
|---|---|---|---|
| `Esc` | 无动作或轻提示 | `pop_screen()` 返回上一页 | 先关闭 Modal / 收起当前态 |
| `Q` | `App.exit()` | `App.exit()` | `App.exit()` |
| `Ctrl+C` | 可作为 Quit 别名 | 可作为 Quit 别名 | 危险操作进行中时先确认 |
| 页面“返回”按钮 | 无 | 与 Esc 相同 | 关闭当前层 |
| 页面“退出”按钮 | `App.exit()` | `App.exit()` | `App.exit()` |

Footer 只展示当前上下文可执行的动作，避免把“取消”“返回”“退出”混在同一个标签中。

### 6. Textual 架构保留或替换

#### 推荐：保留框架和现有导航，补齐共享 UI system

保留：

- Textual 依赖及测试工具；
- `OptionList`、`Select`、`Input`、`Button`、`ProgressBar`、`RichLog`；
- `CommandDeckApp` 的 Screen stack 与 `CommandPage` 起点；
- `RunSetupScreen` 的选择器、校验、命令构建和 parent callback 生命周期；
- 当前 macOS 原生文件/目录选择 helper；
- pipeline 子进程、`run.log.jsonl` 和 Observer reducer/recovery 边界；
- Q detach、X 二次确认停止和竞态处理。

升级或替换：

- 将 `CommandPage` 提升为共享 Screen shell；
- 统一 theme tokens、间距、surface、响应式和 Footer conventions；
- 让 Run Setup 消费同一页面骨架；
- 抽出共享 TaskPresenter / task components；
- Observer 保持独立 App，但复用同一视觉组件和 presentation model；
- 删除页面内硬编码快捷键文本、重复标题结构和互相冲突的状态措辞。

目标结构：

```text
Subtap UI system
├─ shared theme / responsive rules / Footer vocabulary
├─ PageShell（由现有 CommandPage 演进）
├─ task presentation
│  ├─ TaskHeader
│  ├─ OverallProgress
│  ├─ StageList
│  └─ LiveOutput
├─ CommandDeckApp
│  ├─ Home
│  ├─ RunSetupScreen
│  └─ secondary Screens
└─ ObserverDashboard（独立 App）
   └─ 通过 run.log.jsonl 恢复任务状态
```

这是一次页面系统补全，不是重写业务逻辑或进程模型。更换成 Bubble Tea、tview、ratatui 或其他框架会丢弃现有 Python/Textual 组件、测试和业务适配层，同时仍需重新实现同样的 Screen、Grid、Theme、Picker 与 Worker 能力，没有证据表明能解决当前问题。

## 推荐实施顺序

1. **升级 `CommandPage` 为共享 PageShell**：统一标题、主体、notice、Footer 和 Back/Quit 语义，不先改 App hierarchy。
2. **建立全局 theme 与响应式规则**：统一 tokens、间距、surface、内容最大宽度和 60/90/120 列行为。
3. **迁移 Run Setup**：保留现有选择、校验和 command callback，只替换布局与确认呈现。
4. **抽出 task presentation**：统一运行中、完成、失败和历史任务的信息结构。
5. **迁移 Observer 外观**：保持独立 App、日志 reducer、detach 和 stop 语义。
6. **最后重做 Home**：宽屏保留紧凑实体 `SUBTAP` wordmark，普通文本始终是可读主名称；接入当前任务与最近任务摘要。

## GPT-5.6 Sol 设计复核：Calm Task Workbench

请求模型：GPT-5.6 Sol Pro；账号未提供 Pro，实际使用 GPT-5.6 Sol High。首轮进行了官方资料检索，第二轮上传当前本地 main 的 TUI 源码摘要进行一致性复核。

### 三个方向

1. **Compact Workbench / Calm Task Workbench（采用）**
   - 固定任务层级：页面路径、标题与状态、当前工作、上下文信息、动态 Footer。
   - 90 列按页面需要使用两栏，60 列保持相同阅读顺序并折叠为单列。
   - 最适合同时覆盖 Home、Setup、Running、Completed、Failed 和 History。
2. **Guided Workflow（局部使用）**
   - 适合首次启动、复杂配置或危险确认。
   - 不作为普通转录主流程，否则熟练用户需要跨越过多步骤。
3. **Persistent Dashboard（拒绝）**
   - 宽屏视觉丰富，但固定侧栏与状态栏在 60 列失去价值。
   - 会把模型、Chunk、日志等内部概念抬升为产品主概念。

### 统一页面语法

```text
Masthead / Breadcrumb    Subtap / Transcribe / New task
Page title + state       新建字幕                         Ready
Primary work             当前页面真正要完成的任务
Context                  摘要、最近任务、输出、诊断
Dynamic Footer           只显示当前状态下可执行的动作
```

- 日常页面不显示大 Logo、仓库 URL 或版本；这些只在 Home / Doctor 出现。
- Home 宽屏可保留经过快照验证的紧凑实体 `SUBTAP`，高度不超过首屏约 20%；窄屏始终使用普通文本 `SUBTAP`。
- 默认无外框；通过 surface、间距和标题建立层级。边框只用于 Modal、危险确认和严重错误。
- 主题只使用语义角色：neutral、primary、success、warning、error。颜色不单独承担状态含义。
- 内容最大宽度 104；终端更宽时居中，不继续增加第三栏，也不让控件无意义拉伸。

推荐起始 token：

```text
background  #0B0D10    surface  #101419    panel   #151B22
foreground  #E7EAEE    muted    #8A939D
primary     #57C7D4    success  #69C98D    warning #D6A85F
error       #D96B73
```

间距节奏：

```text
页面左右 padding     2
区块间距             2 行
字段间距             1 行
双栏 gutter          2 列
```

### 响应式

- **60–79 列**：全页单列；说明、完整日志和非关键元数据折叠；Footer 可分两行。
- **80–103 列**：Home、Setup、Running 按内容使用两栏；不强制每个页面都双栏。
- **104–120 列**：内容最大 104 列并居中；不增加第三栏。
- **高度低于 24 行**：隐藏说明、最近字幕和展开日志，保留标题、状态、主动作与 Footer。

### Setup

- 保持单页，不改成多步向导。
- 左侧是字段，右侧是实时任务摘要；窄屏按同一阅读顺序堆叠。
- 热词三个动作同行等宽等高；参考文稿和输出目录保持相同的“值 + 操作”行语法。
- “检查设置”进入明确的 Review/Modal，不再让同一按钮第一次按下后悄悄变成“确认并开始”。

### Running / Completed / Failed / History

运行页首先回答四个问题：正在做什么、整体做到哪、任务是否正常、结果将去哪里。

```text
Subtap / Tasks / interview.mov                         [RUNNING]
整体进度 42%  [=================.......................]  00:08:42
当前阶段：语音识别 · 18 / 43

PIPELINE                     LIVE SUBTITLES
[x] 准备                     The product launch is scheduled...
[x] 切段                     We will publish the final...
[>] 语音识别
[ ] 文本清洗                 OUTPUT
[ ] 智能断句                 ~/Movies/Subtap/interview.srt
[ ] 时间轴对齐
[ ] 热词处理                 DETAILS
[ ] 热词学习                 L 展开模型、计数、隐私和完整日志
[ ] 字幕导出

L 详情   F 输出   D 诊断   Esc 返回   Q 退出观察   X 停止
```

- 整体进度拥有唯一的大进度条；当前阶段进度使用较轻的数字或细条，不能与整体进度争夺层级。
- 阶段使用纵向 `StageList`，禁止横向字符串拼接。
- 最近字幕是“任务正在产生价值”的首要证据；未收到字幕时显示“等待字幕事件，任务仍在运行”，不能只写“暂无”。
- Chunk、原始模型 ID、隐私长说明和完整日志进入 Details。
- Completed 显示结果数量、输出路径和下一步；Failed 显示停止阶段与可靠错误摘要，没有错误数据时明确写“日志未提供原因”；History 复用同一只读 task presentation。
- Optional stage 必须来自实际 `pipeline_plan`，不能把不同模块的 `STAGE_ORDER` 粗暴合并成一个全局常量。

## 验收重点

- 从任意二级页按 Esc 都回到进入它的上一页，不结束进程。
- 从任意页面按 Q 都直接退出整个工具。
- 进入 Transcribe 时先显示完整设置页；不自动弹文件选择器。
- 取消文件选择器后设置页状态不丢失。
- 选错文件可以再次选择，不需要退回首页。
- 热词三个操作在 80 列以上同一行且等宽等高；窄终端自动竖排。
- 首页说明位于 logo 下方；窄终端中 `SUBTAP` 始终可正确识别。
- 二级页无顶部 Header/框标题；标题在内容区内。
- 颜色只来自统一 Theme 变量，错误/警告/成功颜色不承担普通装饰。
- 终端宽度变化后无横向截断，Footer 只显示当前可用动作。
- Home、Setup、Running 在 60×56、90×56、120×56 下明显属于同一套产品。
- Running 的阶段列表不横向换行，整体进度与阶段进度不混淆。
- 所有状态在去除颜色后仍能读懂，焦点顺序与阅读顺序一致。
- Q 只退出 UI / Observer，不停止任务；X 只有在可停止状态出现且必须二次确认。

## 一手来源

- [Textual Screens](https://textual.textualize.io/guide/screens/)
- [Textual Layout](https://textual.textualize.io/guide/layout/)
- [Textual Themes](https://textual.textualize.io/guide/design/)
- [Textual App API：responsive breakpoints](https://textual.textualize.io/api/app/#textual.app.App.HORIZONTAL_BREAKPOINTS)
- [Textual Footer：自动显示当前可用 bindings](https://textual.textualize.io/widgets/footer/)
- [Textual Testing：`run_test(size=...)` 与快照测试](https://textual.textualize.io/guide/testing/)
- [Textual 官方 breakpoints 示例](https://github.com/Textualize/textual/blob/06dbeef4bb70fb718236aa418ed658ef4667a126/examples/breakpoints.py)
- [Textual DirectoryTree](https://textual.textualize.io/widgets/directory_tree/)
- [Textual Widgets：Border titles](https://textual.textualize.io/guide/widgets/#border-titles)
- [Posting 官方仓库](https://github.com/darrenburns/posting)
- [Posting `AppHeader` / `AppBody`](https://github.com/darrenburns/posting/blob/56703a11513e8e74e681b4f859f31945b71e746f/src/posting/app.py#L93-L109)
- [Posting 主题化布局](https://github.com/darrenburns/posting/blob/56703a11513e8e74e681b4f859f31945b71e746f/src/posting/posting.scss#L212-L304)
- [K9s Logo 组件](https://github.com/derailed/k9s/blob/436ea2e9f23c5dd2d8e05c3e974220657524ef17/internal/ui/logo.go#L15-L40)
- [K9s 官方按键语义](https://github.com/derailed/k9s/blob/436ea2e9f23c5dd2d8e05c3e974220657524ef17/README.md#L385-L396)
- [lazygit 官方按键语义](https://github.com/jesseduffield/lazygit/blob/292035709f880f33b9f9c90177f1d2fe63f2bd6a/docs/keybindings/Keybindings_en.md#L20-L31)
- [lazygit 配置：图标可关闭](https://github.com/jesseduffield/lazygit/blob/master/docs/Config.md)
