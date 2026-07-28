# Subtap 商业级 TUI 架构审查报告

task_id：subtap-tui-ia-20260726-1547

- 日期：2026-07-26
- 范围：只审查与规划，不实施源码
- 产品范围：Apple Silicon macOS、本地离线字幕工具、Python / Textual
- 目标：统一信息架构、视觉系统、组件语法、页面状态、CLI UX 与验收门

## 直接判断

1. **保留 Python / Textual。** 当前问题不是框架能力不足，而是产品壳层、页面生命周期和状态表达只统一了一半。迁移 Bubble Tea 或 Ratatui 会重写已经存在的文件选择、配置、日志恢复、测试与 Python 业务接口，收益不足以覆盖风险。
2. **当前 TUI 还不是一个完整产品，而是多个已能工作的界面入口。** `CommandDeckApp`、`RunSetupScreen`、`CommandPage`、`ObservePage`、独立 `ObserverDashboard`、兼容入口 `RunSetupApp` 与 legacy ANSI `TuiApp` 同时存在；它们复用了部分主题和断点，但没有共享完整页面语法与生命周期。
3. **最大根因是“命令启动器”与“任务产品”混在一起。** 首页按命令分类；开始任务后主 App 退出，CLI 再启动 pipeline 子进程和第二个 Observer App。用户看到的是页面切换，实际却是 App 生命周期切换。
4. **运行页必须重做信息架构，不应继续修边距。** 91×56 的真实截图同时显示状态、阶段、进度、模型、计数、Chunk、隐私、输出、第二个进度、第二个 Chunk、阶段列表、字幕和第二个输出，造成重复、灰卡片工程感和完成态不明确。
5. **推荐目标是 Subtap Calm Workbench。** 一个 Textual App、一个页面壳层、一个语义主题、一个响应式规则、一个任务呈现模型；pipeline 仍在独立子进程运行，UI 仍只通过 `run.log.jsonl` 观察。
6. **Running、Completed、Failed 不应是三套页面。** 它们是同一个 `TaskScreen` 的三种终态/运行态。History 与 Observe 也不应分成“历史列表”和“手选日志文件”两套产品概念，而应是任务列表进入同一个 `TaskScreen`。

## 事实、决策与缺口

### 已确认事实

| 事实 | 当前证据 |
|---|---|
| 顶层 TTY 入口使用 `CommandDeckApp` | `src/subtap/cli/__init__.py:134-143, 274-279` |
| 首页已有 Transcribe、Batch、Observe、Models、Glossary、Setup、Doctor | `src/subtap/ui/command_deck.py:37-45` |
| Transcribe 已在主 App 内进入 `RunSetupScreen`，并用 `ReviewTaskScreen` 复核 | `src/subtap/ui/command_deck.py:246-251`; `src/subtap/ui/textual_run_setup.py:63-113, 323-367` |
| Models、Doctor 是子进程命令输出页；Setup 仍会退出到 CLI 向导 | `src/subtap/ui/command_deck.py:264-290`; `src/subtap/ui/textual_command_pages.py:134-223` |
| Batch 只有目录选择与启动；不是完整批量工作台 | `src/subtap/ui/textual_command_pages.py:73-131, 389-404` |
| 主 App 内的 Observe 依赖用户手选 `run.log.jsonl` | `src/subtap/ui/textual_command_pages.py:296-408` |
| pipeline 使用独立子进程；Observer 只读 `run.log.jsonl` | `src/subtap/cli/pipeline_cli.py:526-559, 654-683`; `src/subtap/ui/observer.py:58-158, 304-305` |
| `TaskPresentation` 已覆盖运行、完成、失败，但当前视图仍重复字段 | `src/subtap/ui/observer.py:163-240, 393-432` |
| 当前水平断点是 compact `<80`、regular `80–103`、wide `>=104` | `src/subtap/ui/theme.py:9-13` |
| 内容最大宽度已在首页、设置页、二级页和 Observer 使用 104 列 | `src/subtap/ui/command_deck.py:133-137`; `src/subtap/ui/textual_run_setup.py:128-132`; `src/subtap/ui/textual_command_pages.py:32-36`; `src/subtap/ui/observer.py:313-318` |
| 当前 Footer 使用 Textual 原生 `Footer`，但默认 command palette 仍会泄露 | 各页 `Footer()`；91×56 截图显示 `^p palette`，源码未禁用 palette binding |
| legacy `TuiApp`、旧 views 和 `HistoryScanner` 仍存在 | `src/subtap/ui/tui_app.py:33-`; `src/subtap/ui/views/`; `src/subtap/ui/history.py:37-66` |

### 已采用的架构决策

- 继续使用 Textual，不迁移框架。
- `Esc` 只返回或取消一级；`Q` 退出工具。
- Observer 中退出只脱离观察，不停止任务；`X` 只在任务运行时出现，并必须二次确认。
- compact `<80`、regular `80–103`、wide `>=104`；内容最大宽度 104。
- 不新增 TUI 组件依赖；优先使用 Textual 原生 `Screen`、`ModalScreen`、`Footer`、`Grid`、`ProgressBar`、`RichLog`、`OptionList`、`DataTable` 和 breakpoint。
- Observer 数据边界固定为：

```text
pipeline child process
    -> run.log.jsonl
    -> reducer
    -> task presentation
    -> Textual UI
```

UI 不订阅 pipeline 内部 EventBus，也不执行模型推理。

### 暂时无法验证

- 最近两张 91×56 Terminal 截图存在于上游 Codex task，不在仓库中；本报告依据截图文本与可访问的 appshot 上下文审查，无法把原图纳入仓库证据。
- 参考项目 Worker 的最终源码模式尚未回传，本报告不假设能复制 tui-studio 或 vue-tui 的跨语言实现。
- 颜色在 macOS Terminal 不同 profile、iTerm2、16 色、256 色与 TrueColor 下的实际观感，必须做原型和人工验收。
- Textual TUI 对 VoiceOver 的实际可用性未验证；不能声称当前已无障碍。

## 最大问题

### 1. 页面栈统一了，App 生命周期没有统一

当前主路径是：

```text
CommandDeckApp
  -> RunSetupScreen
  -> ReviewTaskScreen
  -> App 返回 CLI command
  -> CommandDeckApp 结束
  -> CLI 启动 pipeline child
  -> CLI 启动独立 ObserverDashboard
```

这解释了为什么 Home、Setup 和 Running 像三个产品。真正需要统一的是生命周期，而不是再建一组视觉组件。

目标路径应是：

```text
SubtapApp
  -> HomeScreen
  -> TranscribeSetupScreen
  -> ReviewTaskModal
  -> TaskScreen
       UI process launches pipeline child
       UI process reads run.log.jsonl
       Esc returns/detaches; Q exits/detaches; X confirms stop
```

pipeline 仍在独立进程；改变的是 UI 不再退出并重启。

### 2. 首页是命令目录，不是任务入口

当前七项平铺菜单对工程结构很诚实，但没有回答用户最常见的三个问题：

1. 我要开始什么任务？
2. 我刚才的任务进行到哪里？
3. 出错后下一步做什么？

首页应以“新建任务 + 最近任务 + 工具与资源”组织，而不是把七个命令放在同一层级。

### 3. 运行页没有单一视觉焦点

截图与源码共同表明：

- `current_work` 同时出现在状态区和独立行；
- 输出在状态区和右侧活动区重复；
- `ASR 草稿 / 已对齐 / 当前模型 / 隐私`占据首屏；
- 完成后只替换几行文字，没有重排主操作；
- 两块 `$surface` 背景面板将内部结构抬升为主要视觉；
- 字幕不是主内容，只是与 pipeline 并列的一块文本。

用户主任务应是“确认任务正在正常前进”和“阅读最近字幕”；模型名、计数、隐私说明属于详情。

### 4. 视觉 token 只统一了颜色入口，没有形成语法

当前共享层只有背景、前景、Footer 与几个 Rich 色值；页面仍各自决定标题、卡片、边框、间距和动作行。结果是“用了同一种青色”，但没有形成商业产品的一致节奏。

### 5. 页面状态覆盖不完整

- `CommandOutputPage` 有 loading / output / command failure。
- `ReviewTaskScreen` 有 confirm / cancel。
- `ObserverDashboard` 有 running / completed / failed / missing output。
- 主 App 内 `ObservePage` 没有进程 return code，只显示“任务记录”，也没有捕获损坏日志错误。
- Models / Doctor 没有专用空态、部分成功、修复建议或分组状态。
- Setup 仍外跳，没有 dirty / validating / saving / saved / error 状态。
- Batch 没有任务队列、逐项状态与总结页。
- History 没有成为主 App 的一等页面。

### 6. 响应式只有宽度，没有低高度验收

横向断点是正确基础，但 40×12、60×18、80×24 等短终端没有统一压缩规则。当前大量固定 `height: 3`、整页说明与 Footer 可能把主操作推到滚动区之外。

### 7. CLI 与 TUI 的语言不一致

CLI 已有 Typer 分组、`--json`、批量 JSONL、退出码和 fail-fast 错误，但：

- 错误有时形成 `✗ 错误：...` 的双重前缀；
- TTY 进度、非 TTY 输出和 JSON stdout/stderr 边界没有统一产品契约；
- TUI 的页面状态没有直接复用 CLI 的统一状态语义；
- `subtap` 无参数在 TTY 打开 TUI，在非 TTY 打印一份无交互 Command Deck，而不是正式 help。

### 8. 设计文档没有单一事实源

`docs/TUI设计.md` 是通用 TUI 学习资料，其中 `q / Esc` 都退出等建议与 Subtap 已采用语义冲突。`docs/adr/0007-single-textual-app-navigation.md` 只有一个决策段落。真正产品约束分散在 ADR、research、plans、AGENTS.md 和源码。

本报告应作为实现前的架构基线；最终采用后需要把稳定约束同步进 ADR 与 AGENTS.md，通用学习资料不能继续充当产品规格。

## 设计原则

1. **任务优先，命令退后。** 页面名称和主操作围绕“新建字幕、观察任务、打开结果、修复失败”，命令名只作为 CLI 入口。
2. **一屏一个主问题。** Home 负责选择下一步；Setup 负责配置；Review 负责确认；Task 负责状态和字幕；Completed 负责交付；Failed 负责恢复。
3. **状态改变布局，不只改变颜色。** 完成态提升结果和打开动作；失败态提升原因、重试和诊断；运行态提升进度和字幕。
4. **一份数据只出现一次。** 进度、耗时、输出、Chunk、模型和计数各有唯一位置。详情数据不重复进入概览。
5. **视觉统一不改变执行边界。** UI 可统一为一个 App，但 pipeline 必须继续运行在独立进程；Observer 只读日志。
6. **Textual 原生能力优先。** 复用 Screen stack、ModalScreen、Grid、Footer、DataTable、RichLog、OptionList、ProgressBar 和 breakpoint；不引入新的 TUI 组件库。
7. **颜色只表达语义，不承担唯一信息。** 每个状态同时使用词语、符号和位置；`NO_COLOR` 下仍可理解。
8. **动态 Footer 只显示当前可执行动作。** 禁止手写 Footer 文案；禁用未使用的 command palette。
9. **紧凑但不拥挤。** 不用整页边框、大灰卡、装饰性 ASCII 或宽屏新增信息栏填满空间。
10. **失败必须可追踪。** 页面显示人能行动的摘要，完整错误保留在日志和诊断页；损坏日志、缺失输出、子进程异常不得被空态吞掉。

## 页面蓝图

### 目标信息架构

```text
SubtapApp
├─ HomeScreen
│  ├─ TranscribeSetupScreen
│  │  └─ ReviewTaskModal
│  │      └─ TaskScreen
│  ├─ BatchSetupScreen
│  │  └─ ReviewBatchModal
│  │      └─ BatchTaskScreen
│  ├─ HistoryScreen
│  │  └─ TaskScreen (live / replay)
│  ├─ ModelsScreen
│  ├─ GlossaryScreen
│  ├─ SetupScreen
│  └─ DoctorScreen
├─ FirstRunScreen
└─ Modals
   ├─ ConfirmStopTaskModal
   ├─ ReviewTaskModal
   ├─ HelpModal
   └─ BlockingErrorModal
```

Running、Completed、Failed 是 `TaskScreen` 状态；History 与 Observe 共用任务详情，不再成为两个并列概念。

### 统一页面语法

```text
Breadcrumb / context      Subtap / New task
Page title + state        新建字幕                         Ready
Primary work              当前页面真正要完成的工作
Context                   只放决策所需的次要信息
Dynamic Footer            仅显示此时可执行动作
```

- Home 不显示 breadcrumb。
- 大 Logo、版本和项目地址只允许出现在 Home；版本与路径诊断也可出现在 Doctor。
- 普通页面不显示页面级边框。
- 页头不做框标题；标题是一行内容。

### 页面与状态矩阵

| 页面 | 主要内容 | 主要动作 | 必须覆盖的状态 | 当前差距 |
|---|---|---|---|---|
| Home | 紧凑品牌、新建任务、最近任务、工具与资源 | Transcribe、Batch、打开最近任务 | first run、无历史、有运行任务、有失败任务 | 当前是七项平铺命令，无最近任务 |
| Transcribe Setup | 媒体、质量、热词表、参考文稿、最大字数、输出目录 | 检查设置、返回 | empty、validating、invalid、ready、picker error | 功能完整，页面语法与状态层级未统一 |
| Review | 输入、关键参数、输出位置、隐私/远程风险变化 | 开始、返回修改 | ready、launching、launch error | 当前 modal 可复用，需缩短摘要并突出差异 |
| Running | 文件名、阶段、总进度、耗时、实时字幕、紧凑阶段列表 | 详情、脱离观察、停止任务 | launching、running、stopping、log error、process lost | 当前信息重复，字幕不居中 |
| Completed | 成功标题、输出文件、耗时、字幕数量、结果动作 | 打开文件、打开目录、返回 Home | result ready、missing output | 当前只是运行页文字替换 |
| Failed | 失败标题、失败阶段、可行动摘要、诊断路径 | 重试、打开诊断、返回 Home | pipeline failure、missing output、corrupt log | 当前只显示退出码与“未生成” |
| History / Observe | 最近任务表：状态、媒体、时间、耗时、输出 | 打开、重新读取、筛选状态 | loading、empty、ready、stale、corrupt record | 当前主 App 要求手选日志；legacy scanner 未接入 |
| Models | 当前模式所需模型、状态、大小、位置、校验结果 | 下载、校验、移除、刷新 | loading、ready、missing、downloading、corrupt、error | 当前只是 `models status` 文本输出 |
| Glossary | default、learned、自定义热词表及所有权说明 | 编辑默认、查看学习结果、打开目录 | empty learned、ready、open error | 当前基础动作已存在，缺少统一资源列表 |
| Setup | 默认模型、字幕默认值、远程服务和隐私边界 | 验证、保存、恢复当前值 | loading、clean、dirty、validating、saved、error | 当前退出 TUI 打开 CLI 向导 |
| Doctor | 总体结论、失败检查、警告、环境与路径 | 重新检查、打开诊断、跳到修复页 | checking、healthy、warning、failed | 当前只是命令文本输出 |
| Batch Setup | 目录、发现文件数、共用参数、输出目录 | 扫描、复核、返回 | empty、scanning、no files、ready、scan error | 当前只有目录选择 |
| Batch Running | 总进度、当前文件、成功/失败/待处理列表 | 详情、脱离观察、停止剩余任务 | queued、running、partial failure、completed、cancelled | 当前完整 dashboard 与主 App 分离 |
| First Run | 设备、模型方案、下载与结果 | 下一步、重试、取消 | checking、ready、downloading、failed、complete | 已有 Screen，但快捷键与统一壳层未对齐 |

### Home

```text
SUBTAP
本地离线字幕生成                                      vX.Y

新建任务
› Transcribe     单个音频或视频生成字幕
  Batch          批量处理一个目录

最近任务
  ▶ 高质量中文语音.mp3       语音识别  22%        00:06
  ✓ interview.mov            已完成              00:50
  × lecture.wav              时间轴对齐失败       昨天

工具与资源
  Models   Glossary   Setup   Doctor
```

- wide 可显示固定、人工校验的紧凑 ASCII wordmark；regular / compact 只显示 `SUBTAP`。
- 最近任务最多显示 3 条，更多进入 History。
- 运行中和失败任务优先于已完成任务。
- 选中态只使用一个 accent 指示：左侧 `›` 或文字色，不能同时使用背景、粗体、箭头和边框。

### Transcribe Setup

```text
Subtap / 新建字幕                                      Ready

媒体文件
[ /Users/.../video.mp4                             ] [选择…]

识别
质量               [ 高质量 · 1.7B                 ]
热词表             [ 默认 · default.txt             ]
[编辑默认] [查看学习结果] [选择其他]

字幕
参考文稿           [ 不使用                         ] [选择…]
最大字数           [ 25 ]  建议 25；范围 10–60
输出目录           [ /Users/.../output               ] [选择…]

[检查设置] [返回]
```

- 同组控件共用 Grid；compact 自动变为一列。
- 用户取消 native picker 时保留页面和值。
- 错误显示在字段组下方并把焦点移到第一个错误字段，不弹普通错误 modal。
- “检查设置”成功后进入 Review，不直接启动。

### Review

Review 只展示会影响结果或风险的字段：

```text
复核任务

输入       高质量中文语音.mp3
质量       高质量 · 1.7B
热词表     default.txt
参考文稿   不使用
字幕       最大 25 字
输出       /Users/.../高质量中文语音.srt
隐私       本地处理；音频不离开设备

[返回修改] [开始转录]
```

- 远程 ASR / LLM 开启时，隐私行必须变成 warning，并明确哪类数据会离开设备。
- 不重复展示内部命令行。
- launching 超过 200ms 时禁用按钮并显示 spinner；启动失败留在 modal，显示原因与“返回修改”。

### TaskScreen：Running

regular / wide：

```text
高质量中文语音.mp3                    语音识别 · 22% · 00:06
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 22%

处理流程                         最近字幕
✓ 音频标准化                    所以，假如你现在要买 GR4……
✓ 音频切段                      对于部分人来说，构图会有点挑战。
▶ 语音识别
· 文本清洗
· 智能断句
· 时间轴对齐
· 热词替换
· 热词学习
· 字幕导出
```

compact：

```text
高质量中文语音.mp3
语音识别 · 22% · 00:06
━━━━━━━━━━━━━━━━━━━━ 22%

▶ 语音识别      2 / 9 阶段

最近字幕
所以，假如你现在要买 GR4……
对于部分人来说，构图会有点挑战。
```

- 概览不显示模型、ASR 草稿数、对齐数、隐私长说明、Chunk id 和完整输出路径。
- `L` 进入详情页/详情层后才显示这些工程指标与最近事件。
- pipeline 列只表达进程；字幕列是主要阅读区。
- 没有字幕时显示“等待语音识别结果”，不能只显示“暂无”。

### TaskScreen：Completed

```text
✓ 字幕已生成                                      00:50

高质量中文语音.srt
/Users/qunqing/Downloads/

39 条字幕 · 9 / 9 阶段完成

[打开字幕] [打开输出目录] [返回首页]
```

- 进度条、活动阶段箭头和“正在运行”动作全部消失。
- 成功结果成为第一视觉焦点。
- 输出缺失时不能进入成功布局，应进入 “Completed / missing output” 错误状态。

### TaskScreen：Failed

```text
× 字幕生成失败

失败阶段    时间轴对齐
原因        ForcedAligner 未生成可用时间轴
工作文件    已保留

[重试任务] [打开诊断] [返回首页]
```

- 首屏只显示可行动摘要，不倾倒 traceback。
- “重试任务”必须复用现有 retry / resume 语义，不能构造假成功或跳过损坏阶段。
- 完整错误、退出码和日志位置进入详情。

### History / Observe

- 使用 `DataTable`：状态、媒体、开始时间、耗时、输出。
- 默认排序：运行中 → 失败 → 最近完成。
- Enter 打开共用 `TaskScreen`。
- live task 每秒读取日志；historical task 使用 replay。
- 保留“选择 run.log.jsonl…”作为次要导入动作，不再是页面主流程。
- 完整 JSON 行损坏时显示失败状态和精确文件/行号；仅允许忽略未完成的最后一行，保持当前 fail-fast 规则。

### Models

- 只显示当前 fast / quality 路径所需模型；高级详情可展开。
- 表格列：模型、用途、状态、大小、位置。
- missing 显示 Download；ready 显示 Verify / Remove；corrupt 显示 Repair。
- 下载进度使用同一 ProgressBar 与状态 token。
- 不复制 ModelRegistry / downloader 业务，只为现有能力建立页面。

### Glossary

- 三类资源必须明确所有权：
  - `default.txt`：用户维护；
  - `learned.txt`：系统自动学习，用户只读查看；
  - 自定义文件：任务级选择。
- 现有“编辑默认 / 查看学习结果 / 打开目录”三项保留。
- learned 不存在时使用空态，不使用 error。
- 打开失败时显示完整原因并保留 Error 日志。

### Setup

- 不再从 TUI 退出到 CLI wizard。
- 页面分为：模型与质量、字幕默认值、远程服务、隐私说明。
- API key 只显示环境变量名，不显示值。
- 保存前验证；保存失败保留用户输入和完整 Error 日志。
- CLI `subtap setup` 继续存在，TUI 与 CLI 调用同一配置服务，不互相调用交互界面。

### Doctor

- 顶部只显示 `Healthy / Warning / Failed`。
- 失败检查排在最前；成功检查默认收起或降低对比度。
- 每项包含：检查名、结果、影响、下一步。
- `doctor --json` 继续作为机器输出契约；TUI 使用同一结构化结果。

### Batch

- Batch Setup 先扫描目录并显示发现数量，再 Review。
- Running 使用总进度 + 当前文件 + compact DataTable。
- 逐项状态：queued、running、succeeded、failed、interrupted。
- 部分失败的终态是“完成但有失败”，不能显示纯成功。
- 复用现有 batch progress / abort 能力，不再保留另一套视觉 dashboard 作为产品入口。

## 视觉系统

以下为**建议 token**，不是已验证成品；必须经过 91×56、80×24、60×18 原型与人工验收后才能固化。

### 色彩 token

| Token | TrueColor | ANSI 256 | ANSI 16 / NO_COLOR | 用途 |
|---|---|---:|---|---|
| `bg.base` | `#0B0F14` | 233 | terminal default | 页面背景 |
| `bg.surface` | `#111820` | 234 | terminal default | 少量分组面 |
| `bg.raised` | `#17212B` | 235 | terminal default | modal / focus surface |
| `border.subtle` | `#2B3744` | 238 | bright black | 分隔线、非主边框 |
| `text.primary` | `#F2F5F7` | 255 | bright white/default | 主文本 |
| `text.muted` | `#98A4B3` | 246 | bright black | 描述与辅助信息 |
| `text.subtle` | `#697583` | 243 | bright black | 非活动阶段 |
| `accent` | `#56D4DD` | 80 | bright cyan | 焦点、主动作、当前状态 |
| `info` | `#78A9FF` | 111 | bright blue | 路径、链接、说明 |
| `success` | `#67D391` | 78 | bright green | 完成 |
| `warning` | `#F3BE63` | 221 | bright yellow | 风险、等待、部分完成 |
| `error` | `#FF6B7A` | 203 | bright red | 失败、危险确认 |

规则：

- 单个页面最多同时使用 accent + 一个状态色；其余使用中性色。
- 不用纯黑大块面板和高饱和霓虹。
- 不以颜色区分唯一状态；始终配合 `✓ / ▶ / ! / × / ·` 与文字。
- `NO_COLOR` 下移除所有颜色与 tint，保留层级、字重、符号和空白。
- 不承诺亮色主题；当前只定义一个经过验证的深色语义主题。若未来确有需求，再增加亮色 token，不做未验证的主题切换。

### 字体与层级

| 层级 | 语法 |
|---|---|
| Brand | 仅 Home wide 使用固定 ASCII；其他尺寸用粗体 `SUBTAP` |
| Page title | 一行、bold、`text.primary`；状态在右侧或下一行 |
| Section | 简短名词、bold；不用边框标题 |
| Body | 默认字重、`text.primary` |
| Description | `text.muted`，最多两行 |
| Path / code | `info` 或默认等宽，不加装饰边框 |

### 边框语法

- 页面：无边框。
- 普通分组：优先空白、对齐、背景差；必要时仅用一条 `─` 分隔。
- 选中项：`›` 或左侧 `▏`，二选一。
- Modal：允许 `round` 边框。
- 危险确认：`error` 边框。
- RichLog / 诊断：可用 subtle border，但默认不在首屏。
- 禁止整页装饰边框、每个字段一张卡、双重边框。

### 字符与降级

| 语义 | Unicode | ASCII fallback |
|---|---|---|
| 完成 | `✓` | `[OK]` |
| 当前 | `▶` | `>` |
| 等待 | `·` | `.` |
| 警告 | `!` | `!` |
| 失败 | `×` | `X` |
| 选中 | `›` | `>` |
| 进度 | `━` / Textual ProgressBar | `=` / `-` |

- CJK 宽度必须使用现有宽度工具或 Textual cell measurement，不用 Python `len()` 做布局。
- 文件路径中间截断，保留文件名和根位置；完整路径可在详情中复制。
- 不依赖 emoji 宽度；状态符号使用单宽可降级字符。

### 空间与密度

- 以 1 行作为基础节奏。
- 页壳左右 padding：compact 1、regular 2、wide 3。
- 页面标题与首个内容块间隔 1 行。
- 同组控件 gutter 1；组间 1 行。
- modal 宽度不超过 `min(64, 92%)`；内容必须可滚动。
- 不为填满宽屏增加无需求侧栏；104 列外保持背景。

## 组件语法

组件是**复用模式**，不要求每项都新建 Python 类。

| 组件/模式 | Textual 基础 | 契约 |
|---|---|---|
| `PageShell` | `Screen` + `VerticalScroll` + `Footer` | max-width 104、统一 padding、标题、内容、动态 Footer |
| `PageHeader` | `Static` / `Horizontal` | breadcrumb、标题、状态；不带页面边框 |
| `FieldGroup` | `Grid` | label、control、help、error 的固定顺序 |
| `ActionRow` | `Grid` / `Horizontal` | 主动作最后或右侧；compact 纵向；按钮同高 |
| `InlineNotice` | `Static` | info / warning / error；持续到用户处理 |
| `StatusBanner` | `Static` | Completed / Failed 等终态首屏焦点 |
| `TaskHeader` | `Static` + `ProgressBar` | 文件名、阶段、总进度、耗时；每项只出现一次 |
| `StageList` | `Static` / `OptionList` | stage 状态列表；compact 只显示摘要，可进入详情 |
| `LiveTranscript` | `RichLog` 或可滚动 `Static` | 最近字幕为运行页主内容；不混日志 |
| `TaskDetails` | `RichLog` / secondary Screen | 模型、Chunk、计数、隐私、事件、日志 |
| `ResourceTable` | `DataTable` | History、Models、Doctor、Batch；固定列、稳定排序 |
| `ReviewModal` | `ModalScreen` | 非破坏性确认；Y/N/Esc 与按钮一致 |
| `DangerModal` | `ModalScreen` | 仅停止任务等危险动作；必须明确后果 |
| `EmptyState` | `Static` + optional action | 说明为什么为空和下一步，不伪装成 error |
| `LoadingState` | `LoadingIndicator` / spinner | 超过 200ms 才显示；保持页面结构稳定 |

`TaskPresentation` 应从当前 `src/subtap/ui/observer.py:43-55` 演进，而不是另建第二个 task model。建议增加或明确：

```text
identity: task_id, media_name
status: queued | running | completed | failed | cancelled | unknown
connection: live | replay | stale
progress: overall_percent, stage, elapsed
stages: ordered stage states
content: recent_subtitles
result: output_path, output_exists
failure: summary, exit_code, diagnostic_path
actions: can_cancel, can_retry, can_open_output, can_open_diagnostics
```

`connection` 是观察状态，不是 pipeline 状态；“退出观察”不能把任务标记为 cancelled。

## 响应式规则

### 宽度

| 模式 | 范围 | 布局 |
|---|---:|---|
| compact | `<80` | 单列；无 ASCII logo；动作纵向；Task 只显示当前阶段摘要，详情另开 |
| regular | `80–103` | 单列页面；Task 可用 2fr/3fr 双列；Home 最近任务保持一列 |
| wide | `>=104` | 内容仍最大 104；Home 可显示固定 logo；Task 双列；不新增第三栏 |

边界必须测试 79 / 80 / 103 / 104 四个宽度，不只测试每档中间值。

### 高度

高度不新增第二套复杂状态机，使用滚动、固定页头和内容优先级降级：

| 高度 | 规则 |
|---:|---|
| `>=28` | 完整节奏 |
| `18–27` | 去掉说明性空行；页头一行；内容滚动；Footer 保持可见 |
| `<18` | survival mode：隐藏品牌、描述和非关键统计；只保留标题、当前状态、主内容与当前动作 |

### 最小尺寸目标

- 舒适尺寸：80×24。
- 必须可操作：60×18。
- 生存尺寸：40×12，允许滚动，但不能出现控件不可达、modal 超出或 Footer 覆盖内容。
- 真实截图回归尺寸：91×56。

### 各页降级

| 页面 | compact | regular / wide |
|---|---|---|
| Home | 单列、无 logo、最近任务 2 条 | 最近任务 3 条，wide 可显示 logo |
| Setup | FieldGroup 全部纵向 | 同组控件同行 |
| Review | 单列、滚动、按钮纵向 | 64 列 modal、按钮同行 |
| Running | 阶段摘要 + 字幕 | 阶段列表 + 字幕双列 |
| Completed / Failed | 单列结果 | 结果和动作仍单列，不为宽屏加统计栏 |
| History / Models / Doctor | 隐藏次要列或进入详情 | 完整 DataTable |
| Batch | 当前项 +摘要 | 总表 + 当前项 |

## 状态反馈

### 三个正交状态轴

不得用一个字符串同时承担数据、任务与页面请求状态。

1. **任务状态**：queued、running、completed、failed、cancelled、unknown。
2. **观察状态**：live、replay、stale、detached。
3. **请求状态**：idle、loading、ready、empty、error。

### 反馈规则

| 事件 | 首屏反馈 | 详情/日志 | 动作 |
|---|---|---|---|
| picker 取消 | 保持原值，不显示错误 | 无 | 继续当前页 |
| picker 启动失败 | 字段组内 error | Error 日志含 stderr | 重试 |
| 验证失败 | 对应字段 error，焦点移入 | 可列全部错误 | 修改 |
| 启动中 | 按钮禁用 + “正在启动” | child log | 等待 |
| 日志尚未出现 | “等待任务日志” | child log path | 等待/诊断 |
| 完整日志行损坏 | Failed / log error | 精确文件与行号 | 打开诊断 |
| 运行中 | 阶段、总进度、耗时、字幕 | 模型/Chunk/事件 | 详情、脱离、停止 |
| 停止请求 | warning “正在停止” | signal 与退出码 | 禁止重复 X |
| 完成 | 成功结果布局 | 总结 | 打开文件/目录 |
| 成功退出但输出缺失 | error，不显示成功 | 预期路径 | 诊断/重试 |
| pipeline 失败 | 失败阶段 + 可行动原因 | traceback / exit code | 重试/诊断 |
| 部分批量失败 | warning “完成但有失败” | 失败文件列表 | 重试失败项 |
| 脱离观察 | TUI 退出后打印 task id、日志和恢复命令 | child 继续运行 | `subtap observe ...` |

### 进度

- 只显示一个 overall ProgressBar。
- 当前阶段显示在 ProgressBar 同一信息组。
- overall progress 沿用现有 pipeline plan 的单调计算，不回退。
- 未知总进度显示 indeterminate，不伪造百分比。
- ETA 未经稳定数据验证前不显示。
- Batch 同时显示 overall items 和当前 item stage，但不能把两个百分比混成一个。

### 错误

页面错误固定为：

```text
发生了什么
为什么影响任务
用户现在能做什么
诊断信息在哪里
```

不在首屏显示 traceback，不吞异常，不返回默认假数据。损坏日志、缺失输出、命令非零退出码必须保留原始证据。

## 键盘语义

| Key | 全局语义 | 条件 |
|---|---|---|
| `Esc` | 关闭 modal；否则返回一级 | Home 不退出 |
| `Q` | 退出 TUI | Task 中只脱离观察，pipeline 继续 |
| `X` | 停止任务 | 仅 running 可见；必须确认 |
| `Enter` | 执行当前主动作 | 不绑定危险操作 |
| `Tab` / `Shift+Tab` | 切换焦点 | 表单和动作区 |
| `↑↓` / `J K` | 列表移动 | Home、History、DataTable |
| `L` | 详情 | Task 有详情时 |
| `F` | 打开输出目录 | 仅输出存在时 |
| `D` | 打开诊断 | 仅诊断存在时 |
| `?` | 帮助 modal | 原型验收后再决定是否保留 |

规则：

- Footer 读取当前 Screen bindings；不可执行动作通过 `check_action` 隐藏。
- 明确禁用 Textual 默认 command palette binding，成品 Footer 不出现 `^p palette`。
- Footer 不重复页面中已有的按钮说明。
- Home 数字键可保留为加速键，但默认不显示，不能改变选项顺序后失效。
- First Run 的 Esc 不能继续使用“取消/退出”混合语义，必须区分取消下载、返回与退出。

## CLI UX

### 保留的基础

- 继续使用现有 Typer / Rich；不新增 CLI 框架。
- 保持现有直接命令和脚本入口。
- 保持 `0` 成功、`1` 运行失败、Typer usage error、`130` 用户中断的既有语义。
- 保留 `--json` 和 batch JSONL；机器输出不得受 TUI 改造影响。

### 顶层命令结构

```text
字幕工作流
  run
  batch-transcribe
  observe
  resume
  retry

本地资源
  models
  glossary
  setup

帮助与检查
  doctor
  version
  demo

交互界面
  tui
```

隐藏的 prepare / transcribe / clean / segment / align / export 继续作为内部阶段，不进入普通帮助。

### 无参数行为

- TTY：打开 `SubtapApp`。
- 非 TTY：输出正式 concise help，不输出带选择箭头和 Footer 的 Command Deck。
- `subtap tui`：显式打开 TUI。
- `TERM=dumb` 或无法进入 alternate screen：使用 plain CLI 提示和直接命令，不输出控制字符。

### Help 结构

每个公开命令固定顺序：

```text
一句话用途
Usage
Arguments
Options
Examples
Outputs
Exit status / failure notes
```

- 帮助示例使用项目真实 Apple Silicon macOS 路径与本地处理语义。
- 参数名称与 TUI 字段一致：媒体文件、质量、热词表、参考文稿、最大字数、输出目录。
- 不在 help 中暴露内部 observer-child / no-tui 开关。

### 错误输出

统一为：

```text
Error: 无法生成字幕
Cause: 时间轴对齐未产生可用结果
Next: 运行 `subtap doctor`，或查看 ...
```

- `_handle_error()` 负责前缀；调用方不得再传入“错误：”，避免 `✗ 错误：...`。
- 人类输出写 stderr；`--json` stdout 必须保持纯 JSON，错误也应使用稳定 JSON 对象或 stderr + 非零退出码，需在实现前固定一种契约。
- 不把 usage error、环境错误和 pipeline failure 混成相同说明。

### Progress

| 环境 | 输出 |
|---|---|
| TTY | 原地更新 ProgressBar、阶段、耗时 |
| redirected / pipe | append-only 行，不输出 cursor control |
| `--json` | stdout 只输出 JSON；进度使用已声明的 JSONL 通道或关闭 |
| `NO_COLOR` | 无 ANSI 色，符号与文字保留 |

完成收据固定包含：状态、输出路径、耗时、字幕条数、下一步命令。失败收据固定包含：失败阶段、诊断路径、退出码。

### TUI / CLI 共用边界

- TUI 不通过解析 CLI 彩色文本获取业务状态。
- Models、Doctor、Setup、Glossary 应调用与 CLI 相同的结构化服务。
- CLI 仍可独立运行；TUI 不成为业务必需依赖。
- pipeline 事件与 `run.log.jsonl` 是 Task UI 的事实源，不能再新增一套 UI 私有状态日志。

## 终端兼容与无障碍

### 必须支持

- macOS Terminal 与 iTerm2。
- TrueColor、ANSI 256、ANSI 16、`NO_COLOR`。
- `TERM=xterm-256color`、`TERM=screen-256color`、`TERM=dumb` 的降级路径。
- CJK、英文、长文件名、空格和 Unicode 路径。
- 全键盘操作；鼠标只是可选增强。

### 无障碍基线

- 状态不只使用颜色。
- 焦点具有符号或反相，不只使用细微色差。
- 所有动作可用键盘完成。
- Footer 与按钮使用相同动词。
- 动画不高频闪烁；spinner 更新不超过正常 Textual refresh。
- `NO_COLOR` 和 plain CLI 提供完整功能路径。
- VoiceOver 无法在当前只读审查中确认；必须人工测试。若 Textual 屏幕阅读不可用，需明确文档化 CLI / JSON 等价路径，不能声称 TUI 已完全无障碍。

## 迁移路线

### Phase 0：冻结基线与视觉原型

改动：无产品源码。

- 固定本报告的 IA、状态模型、键盘语义和 token 候选。
- 为 Home、Setup、Running、Completed、Failed 各做 Textual 原型或最小 Screen spike。
- 固定尺寸：120×40、104×30、103×30、91×56、80×24、79×24、60×18、40×12。
- 人工确认颜色、密度、字幕换行、完成/失败差异、Footer 与 modal。

门：人工明确接受后才能进入实现。未通过时改规格，不在生产页追加补丁。

### Phase 1：共享壳层与主题

- 扩展 `theme.py` 为语义 token。
- 把 `CommandPage` 演进为统一 `PageShell`。
- 统一 Footer、padding、max-width、焦点与断点。
- 禁用 command palette。
- 不改命令行为和 pipeline。

门：Home / Setup / CommandOutput / Glossary 在四个宽度边界行为一致；现有交互测试全通过。

### Phase 2：Home、Setup、Review

- Home 改为“新建任务 + 最近任务 + 工具资源”。
- 保留现有 native picker 与 command 生成。
- Setup 与 Review 消费统一壳层和状态反馈。
- First Run 对齐 Esc / Q 语义。

门：命令参数与当前 CLI parser 完全一致；picker 取消、失败、重选、字段错误和 review 返回均有测试。

### Phase 3：统一 TaskPresentation 与任务视觉

- 先扩展现有 `TaskPresentation`。
- Running / Completed / Failed 使用同一个布局状态机。
- `ObserverDashboard` 与主 App `ObservePage` 先共用相同 presenter 和组件。
- 删除重复字段，详情进入 TaskDetails。

门：现有 event log reducer、单调进度、损坏行 fail-fast、输出缺失、停止确认测试保持通过；91×56 人工验收通过。

### Phase 4：单一 Textual App 生命周期

- `SubtapApp` 在不退出主 App 的情况下启动 pipeline child。
- `TaskScreen` 只读日志。
- Esc / Q 只脱离观察；X 才终止 process group。
- 移除第二次启动 `ObserverDashboard` 的产品路径。

门：

- pipeline child 与 UI 进程隔离；
- UI 不 import pipeline EventBus；
- Q 后 child 继续；
- X 确认后 SIGTERM / SIGKILL 逻辑保持；
- TUI crash 后仍可用 `subtap observe` 恢复；
- 无孤儿或误杀进程。

### Phase 5：History、Models、Glossary、Setup、Doctor、Batch

- History / Observe 统一。
- Models / Doctor 从文本输出页升级为结构化页面。
- Setup 不再退出 TUI。
- Batch 复用统一 task presentation 与 DataTable。

门：每页的 loading / empty / ready / error 状态有自动测试；危险操作有确认；CLI 仍可独立使用。

### Phase 6：CLI UX 与兼容

- 统一 help、error、progress、non-TTY、NO_COLOR、JSON 边界。
- 不改公开命令名称与既有参数含义。
- 加入 stdout / stderr / exit code 合约测试。

门：TTY、pipe、JSON、NO_COLOR、TERM=dumb 全部通过；脚本输出无控制字符。

### Phase 7：删除重复入口与同步文档

- 在确认无调用方后删除 legacy `TuiApp`、兼容 `RunSetupApp`、独立 dashboard 或旧 views 中已被替代的代码。
- 更新 ADR-0007、AGENTS.md、TUI reference 与用户帮助。
- `graphify update .` 更新知识图。

门：代码搜索无旧入口调用；文档只保留一个产品事实源；人工整体验收通过。

## 验收矩阵

### 页面与状态

| ID | 场景 | 自动验证 | 人工视觉验收 | 通过条件 |
|---|---|---|---|---|
| IA-01 | Home 无历史 | pilot + DOM 断言 | 是 | 主动作明确；无空灰卡；工具降级 |
| IA-02 | Home 有 running / failed / completed | 排序测试 | 是 | running、failed 优先；状态不靠颜色 |
| IA-03 | Transcribe 未选文件 | 交互测试 | 是 | 开始不可用或给出字段错误；页面不退出 |
| IA-04 | picker 取消 / 失败 / 重选 | mock picker | 是 | 取消保值；失败可见；重选成功 |
| IA-05 | Review 返回 / 确认 / 启动失败 | modal callback 测试 | 是 | 返回不丢值；失败不关闭页面 |
| IA-06 | Running 0%、22%、未知进度 | reducer + pilot | 是 | 单一进度；字幕为主；无重复字段 |
| IA-07 | Completed 正常输出 | process/output fixture | 是 | 结果与主动作成为焦点；运行控件消失 |
| IA-08 | Completed 但输出缺失 | fixture | 是 | 不显示成功；提供诊断 |
| IA-09 | Failed | non-zero fixture | 是 | 显示失败阶段、摘要、诊断与重试 |
| IA-10 | Cancel 确认 / 取消 | process group tests | 是 | X 仅 running；N/Esc 不停止；Y 停止 |
| IA-11 | Q / Esc 脱离观察 | child process test | 是 | child 继续；终端打印恢复信息 |
| IA-12 | History empty / ready / stale | task fixtures | 是 | 空态有下一步；列表排序稳定 |
| IA-13 | 损坏完整日志行 | parser test | 否 | 明确失败并指出文件/行号 |
| IA-14 | 未完成最后日志行 | parser test | 否 | 只忽略最后半行，不吞其他错误 |
| IA-15 | Models missing / downloading / ready / corrupt | service fixtures | 是 | 动作随状态变化 |
| IA-16 | Glossary learned 不存在 / 打开失败 | resource fixtures | 是 | 不存在为空态；打开失败为 error |
| IA-17 | Setup dirty / invalid / saved / save error | config fixtures | 是 | 输入保留；失败可追踪 |
| IA-18 | Doctor healthy / warning / failed | JSON fixtures | 是 | 失败优先；下一步明确 |
| IA-19 | Batch empty / running / partial failure / complete | batch fixtures | 是 | 部分失败不显示纯成功 |
| IA-20 | First Run 下载失败 / 重试 / 取消 | 现有 first-run tests 扩展 | 是 | 键盘语义与主 App 一致 |

### 响应式

| ID | 尺寸 | 自动验证 | 人工验收重点 |
|---|---:|---|---|
| R-01 | 120×40 | `run_test(size=...)` + snapshot | 内容保持 104，不产生第三栏 |
| R-02 | 104×30 | breakpoint 断言 | wide 起点无跳动 |
| R-03 | 103×30 | breakpoint 断言 | regular 不残留 wide logo |
| R-04 | 91×56 | snapshot + appshot 对比 | 修复真实截图重复、灰卡、留白和 Footer |
| R-05 | 80×24 | breakpoint 断言 | regular 起点控件不挤压 |
| R-06 | 79×24 | breakpoint 断言 | compact 单列、按钮同宽 |
| R-07 | 60×18 | focus traversal test | 全部控件可达；modal 可滚动 |
| R-08 | 40×12 | focus traversal test | survival mode 可完成返回/退出；Footer 不覆盖 |

### 终端与输出

| ID | 环境 | 验证 |
|---|---|---|
| T-01 | macOS Terminal TrueColor | 人工检查颜色、边框、CJK、焦点 |
| T-02 | iTerm2 TrueColor | 人工检查颜色与键盘 |
| T-03 | ANSI 256 | token 映射 + 人工检查 |
| T-04 | ANSI 16 | 状态符号与对比度 |
| T-05 | `NO_COLOR=1` | 无 ANSI 色；所有状态仍可辨 |
| T-06 | `TERM=dumb` | plain CLI，无 alternate screen / cursor code |
| T-07 | stdout pipe | 输出 append-only，无控制字符 |
| T-08 | `--json` | stdout 可直接 `json.loads()`；无进度/装饰污染 |
| T-09 | CJK / 英文 / 长路径 | 列对齐、路径中间截断、完整值可查看 |
| T-10 | VoiceOver | 人工验证；失败时确认 CLI/JSON 等价路径与文档说明 |

### 视觉验收

以下决策必须原型与人工确认，不能由单元测试代替：

1. TrueColor palette 在 macOS Terminal 与 iTerm2 的对比、冷暖和疲劳度。
2. wide 固定 ASCII wordmark 的字形、占高和 104 列边界。
3. 91×56 Running 页中 pipeline / transcript 比例。
4. compact 下阶段摘要是否仍能建立任务进度感。
5. 中文字幕换行、标点、数字与英文单词混排。
6. Completed 与 Running 是否第一眼可区分。
7. Failed 是否明确但不过度警报化。
8. Footer 是否只显示真实动作，且不再出现 `^p palette`。
9. 40×12 modal、滚动与焦点是否可用。
10. NO_COLOR 下焦点、状态与危险操作是否仍清楚。

### 发布门

必须同时满足：

- 自动：页面状态、event log reducer、process boundary、键盘、断点、CLI 输出合约通过。
- 人工：Home、Setup、Running、Completed、Failed、History、Models、Glossary、Doctor、Batch 在目标终端和尺寸通过。
- 架构：UI 未连接 pipeline EventBus；退出观察不停止任务；X 不可误触。
- 文档：ADR、AGENTS.md、TUI 设计事实源同步。
- 代码：无重复入口仍被产品路径调用；无新 TUI 依赖；无被吞掉的错误。

## 当前源码引用

| 主题 | 位置 |
|---|---|
| 顶层 CLI、TTY 入口、Command Deck 结果处理 | `src/subtap/cli/__init__.py:41-47, 83-143, 260-304` |
| pipeline child、Observer 启动与退出语义 | `src/subtap/cli/pipeline_cli.py:42-59, 436-441, 526-559, 654-683` |
| Home 选项、断点、布局、Screen routing | `src/subtap/ui/command_deck.py:37-55, 122-218, 246-320` |
| 共享断点、Textual CSS 与 ANSI / NO_COLOR | `src/subtap/ui/theme.py:9-30, 33-60, 83-109` |
| Setup、Review、picker、验证与兼容 App | `src/subtap/ui/textual_run_setup.py:24-113, 118-248, 264-367, 390-419` |
| 二级页、命令输出、Glossary、Observe、Batch picker | `src/subtap/ui/textual_command_pages.py:24-70, 73-223, 225-408` |
| event log reducer 与 TaskPresentation | `src/subtap/ui/observer.py:43-240` |
| Observer UI、Footer、详情、输出、诊断、停止确认 | `src/subtap/ui/observer.py:253-519` |
| legacy ANSI TUI | `src/subtap/ui/tui_app.py:33-` |
| legacy history 与 pipeline 状态映射 | `src/subtap/ui/history.py:13-66`; `src/subtap/ui/state.py:12-93` |
| Command Deck / setup / responsive 测试 | `tests/test_command_deck.py`; `tests/test_textual_run_setup.py`; `tests/test_textual_first_run.py` |
| reducer / observer / process group 测试 | `tests/test_observer.py:15-699` |
| 当前框架方向 ADR | `docs/adr/0007-single-textual-app-navigation.md` |
| Observer 解耦 ADR | `docs/adr/0005-event-bus-for-ui-decoupling.md` |
| 当前成熟项目复用审查 | `docs/research/2026-07-26-tui-mature-projects-reuse-review.md:7-18, 345-354` |
| 当前一手资料与架构建议 | `docs/research/2026-07-26-tui-redesign-primary-source-review.md:6-46, 220-374` |
| Running 页参考审查 | `docs/research/2026-07-16-tui-task-running-page-patterns.md` |

## 最终建议

**推荐方案：在 Textual 内完成 Calm Workbench 收敛，不迁移框架，不新增依赖。**

第一阶段不要实现所有页面。先用真实 91×56 截图问题作为门，原型验证 Home、Running、Completed、Failed 和 compact 布局；通过后再抽共享壳层与 TaskPresentation。最危险的改动是“单一 App 启动 child 并保持可恢复观察”，必须晚于视觉与 presenter 收敛，并用现有 process-group、日志恢复和 fail-fast 测试守住边界。

result_correlation_id：ia-20260726
