# TUIStudio / Vue TUI 与官方 TUI 框架参考研究

> task_id: `subtap-tui-refs-20260726-1547`
> 调研日期：2026-07-26
> 范围：只读官方仓库、源码、README、许可证和官方文档；不修改 Subtap 源码。
> 结论等级：事实来自链接的一手资料；“建议”是结合 Subtap 当前架构后的推论。

## 结论

1. **保留 Python/Textual，不迁移到 Go、Rust 或 Vue。** Textual 已经覆盖 Subtap 需要的 Screen、ModalScreen、Grid、响应式断点、主题变量、Footer、ProgressBar、RichLog 和可测试交互。当前缺口是共享页面系统和信息层级，不是框架能力不足。
2. **TUIStudio 只作为视觉工作台参考。** 它最值得借鉴的是“终端字符单元格预览 + 三栏工作区 + 层级树 + 属性面板 + command palette + undo/redo”。其源码是 React/TypeScript/Web 编辑器，不能直接成为 Subtap 的运行时组件。
3. **Vue TUI 只作为渲染边界和高吞吐信息面的参考。** 它把 cell buffer、render plane、DOM renderer、stdout renderer 和 CLI host 分开，这个分层理念可映射到 Subtap 的 `presentation -> Textual UI`；Vue、Node、stdout renderer 本身不可迁移。
4. **Bubble Tea 与 Ratatui 只提供架构和交互语义参考。** Bubble Tea 的 Elm-style `Model -> Update -> View`、Bubbles/Lip Gloss 的职责分离，以及 Ratatui 的 immediate-mode + constraint layout 都有价值；二者都不会自动替 Subtap 解决 Screen 导航、Observer 进程边界或事件循环。
5. **Observer 边界不变：** `pipeline -> run.log.jsonl -> reducer/presentation -> UI`。视觉统一应复用语义 token 和任务呈现模型，不应把 pipeline 放进 Textual Worker，也不应让退出观察误杀任务。

## 官方项目逐项核验

### 1. jalonsogo/tui-studio

**已确认事实**

- 官方 README 将项目定义为“用于构建 Terminal UI 的可视化设计工具”，当前标为 alpha；功能包含 live ANSI preview、20+ 组件、Absolute/Flexbox/Grid、主题、层级树、属性面板、undo/redo、`.tui` JSON、command palette 和多框架导出。[README](https://github.com/jalonsogo/tui-studio/blob/main/README.md)
- 本次检查的 GitHub 页面显示约 1.5k stars、134 commits；这说明它有足够参考价值，但 alpha 状态不等于生产级运行时保证。[仓库](https://github.com/jalonsogo/tui-studio)
- `App.tsx` 将 `Toolbar`、`LeftSidebar`、`Canvas`、`PropertyPanel` 注入 `EditorLayout`，command palette 独立挂在编辑器外层。[App.tsx](https://github.com/jalonsogo/tui-studio/blob/main/src/App.tsx)
- `EditorLayout.tsx` 是三栏编辑器壳层，左右栏默认约 256px/320px，并提供拖拽调整宽度。[EditorLayout.tsx](https://github.com/jalonsogo/tui-studio/blob/main/src/components/editor/EditorLayout.tsx)
- `Canvas.tsx` 以 terminal cell 的宽高、zoom、pan、grid 和布局引擎渲染预览；选中/拖拽/锁定/隐藏等状态属于编辑器交互，不是终端运行时协议。[Canvas.tsx](https://github.com/jalonsogo/tui-studio/blob/main/src/components/editor/Canvas.tsx)
- `ComponentTree.tsx` 负责层级选择、展开折叠、可见性、锁定、重命名和重排；`CommandPalette.tsx` 把组件创建、保存、导出、主题和帮助集中成可搜索命令。[ComponentTree.tsx](https://github.com/jalonsogo/tui-studio/blob/main/src/components/editor/ComponentTree.tsx)、[CommandPalette.tsx](https://github.com/jalonsogo/tui-studio/blob/main/src/components/editor/CommandPalette.tsx)
- 技术栈是 React 19、TypeScript 5.8、Vite 7、Zustand 5、Tailwind CSS 和 Lucide React；`package.json` 还包含浏览器端 Playwright/ESLint/Prettier 工具链。[package.json](https://github.com/jalonsogo/tui-studio/blob/main/package.json)

**判断**

- 视觉理念可学：**采用**字符单元格作为布局校准单位；**采用**固定的工作区职责顺序（导航/任务树 — 主工作面 — 属性/动作）；**采用**命令 palette 作为不打断当前页面的次级入口；**采用**“可见/锁定/选中/进行中”状态反馈。
- 源码可复用：**不建议直接复用**。许可证允许复制，但代码依赖 React DOM、Zustand、Tailwind、浏览器 Pointer/Keyboard Event 和像素布局；迁入 Python/Textual 后仍需重写状态、渲染和输入处理。
- 架构不可迁移：**拒绝迁移**。TUIStudio 是“设计 TUI 的 Web 编辑器”，不是 Subtap 的任务运行时，也不理解 `run.log.jsonl`、独立 pipeline 或 Observer 生命周期。

**对 Subtap 的具体映射**

| TUIStudio 模式 | Subtap 改造后的落点 | 处理意见 |
|---|---|---|
| 三栏工作区 | wide：左侧任务/阶段摘要，中间当前任务，右侧动作/输出；regular：收窄为主区加可切换详情；compact：单列 | 采用信息关系，不复制 256/320px 像素值 |
| Layers/Component Tree | Observer 的阶段列表、运行状态和最近字幕；选中项进入详情 | 改造成任务语义，不引入可编辑节点树 |
| Property Panel | Run Setup 的分组设置、校验、输出位置和当前动作 | 用现有 Textual `Grid`/`Select`/`Input`/`Button` |
| Live ANSI Canvas | 以字符宽度、阶段状态和进度为基础的稳定状态面 | 采用字符单元格意识，拒绝渐变背景和浏览器 canvas |
| Command Palette | `?` 帮助、页面动作和不常用设置的集中入口 | 复用现有 Screen/Binding，避免第二套导航栈 |
| Undo/Redo | 不迁移 | Subtap 的 pipeline 与设置不是 TUIStudio 的树编辑模型；只有明确需要可撤销编辑时再单独设计 |

### 2. Simon-He95/vue-tui

**已确认事实**

- 官方 README 将其定义为 Vue 3 terminal UI toolkit，可渲染到 browser DOM、真实 CLI stdout 和 headless tests；定位包含 dashboard、streaming markdown、log viewer、virtual list 和 agent console。[README](https://github.com/Simon-He95/vue-tui/blob/main/README.md)
- 本次检查的 GitHub 页面显示约 186 stars、690 commits；package 当前为 `1.1.2`，许可证字段和仓库 `license` 文件均为 MIT。[仓库](https://github.com/Simon-He95/vue-tui)、[package.json](https://github.com/Simon-He95/vue-tui/blob/main/package.json)、[license](https://github.com/Simon-He95/vue-tui/blob/main/license)
- README 声明 Vue 是 peer dependency，支持 `>=3.3.0 <4`；CLI/runtime 消费者支持 Node.js `>=16.17`。公开 entry points 区分 browser-safe root、`/core`、`/cli`、`/markdown`、`/observability` 和 experimental 入口，并明确不应 deep-import `dist`。[README](https://github.com/Simon-He95/vue-tui/blob/main/README.md)
- `src/index.ts` 暴露 terminal、DOM renderer、theme 和 Vue 组件；`src/core.ts` 暴露 ANSI、cell width、buffer、style、hyperlink sanitization 和 render plane 类型。[src/index.ts](https://github.com/Simon-He95/vue-tui/blob/main/src/index.ts)、[src/core.ts](https://github.com/Simon-He95/vue-tui/blob/main/src/core.ts)
- 官方 README 的核心分层是：`createTerminal({ cols, rows })` 管理 cell buffer/cursor/planes/scrollback；`createDomRenderer` 画 DOM；`createStdoutRenderer` 输出 ANSI；`createTerminalApp` 提供 headless CLI/runtime；`TRenderPlane` 把 transcript、chrome、input、overlay 分面。[README](https://github.com/Simon-He95/vue-tui/blob/main/README.md)
- README 将 `TTranscriptView`、`TLogView`、`TVirtualList` 等列为 experimental；不能把实验入口当稳定公共 API。[README](https://github.com/Simon-He95/vue-tui/blob/main/README.md)

**判断**

- 视觉理念可学：**采用**高吞吐日志/Transcript 的“追加、滚动、分层”语义；**采用**将主内容、输入、状态 chrome 和 overlay 视为不同 surface 的思路；**采用** browser-safe host 与 CLI-only host 分界。
- 源码可复用：**不建议直接复用**。MIT 允许复制，但实现依赖 Vue 3、TypeScript、Node CLI、ANSI buffer 和 DOM/stdout renderer；对 Python/Textual 没有运行时兼容性。
- 架构不可迁移：**拒绝迁移**。Subtap 不需要浏览器 renderer，也不能用 Vue TUI 的 CLI host 替换 pipeline 子进程和 `run.log.jsonl` 恢复协议。

**对 Subtap 的具体映射**

| Vue TUI 模式 | Subtap 对应概念 | 采用边界 |
|---|---|---|
| cell buffer / width provider | 现有 `get_display_width` 与 `truncate_by_width`；页面宽度按终端列数计算 | 采用字符宽度规则，不引入 JS buffer |
| `TRenderPlane` | `status`、`pipeline-pane`、`activity-pane`、`details`、Footer | 采用 surface 分层，但仍由同一个 Textual presentation model 驱动 |
| append-only log / transcript | `RichLog` 详情面，默认最多 200 行、按需展开 | 采用；日志来源继续是 `run.log.jsonl` |
| markdown/transcript stream | 最近字幕与阶段事件的稳定摘要 | 改造；不渲染模型内部噪声，不引入 Markdown runtime |
| host boundary | pipeline process、log reader、UI 三层边界 | 强制保留，不能由 Vue/Node runtime 取代 |

## 官方框架能力边界

### Bubble Tea / Bubbles / Lip Gloss

- Bubble Tea 官方 README 明确是 Go、Elm Architecture 风格的 terminal framework，核心是 model 状态与 `Init`、`Update`、`View`，并提供 cell-based renderer、颜色降采样、keyboard/mouse、clipboard 等能力。[Bubble Tea README](https://github.com/charmbracelet/bubbletea/blob/main/README.md)
- Bubbles 是独立的常用组件库；Lip Gloss 是独立的样式、格式和布局库。Bubble Tea README 还把 Harmonica（动画）和 BubbleZone（鼠标区域）作为周边库列出，说明这些不是核心框架自动提供的同一层能力。[Bubbles README](https://github.com/charmbracelet/bubbles/blob/main/README.md)、[Lip Gloss README](https://github.com/charmbracelet/lipgloss/blob/main/README.md)
- 三者官方许可证均为 MIT。[Bubble Tea LICENSE](https://github.com/charmbracelet/bubbletea/blob/main/LICENSE)、[Bubbles LICENSE](https://github.com/charmbracelet/bubbles/blob/main/LICENSE)、[Lip Gloss LICENSE](https://github.com/charmbracelet/lipgloss/blob/main/LICENSE)

**Subtap 结论：** 采用 `Model -> Update -> View` 的单向状态思维和“组件库/样式库分职责”的设计纪律；拒绝迁移 Go、Lip Gloss 或 Bubbles 源码。Bubble Tea 核心没有 Textual 同等的 CSS/Screen 产品壳层，复杂导航仍由应用自行组织；它也不定义 Subtap 的 Observer process contract。

### Textual

- 官方文档把 Textual 定义为 Python framework，提供 terminal/browser 运行形态、CLI 集成、跨平台能力和 MIT 许可证。[Textual 官方文档](https://textual.textualize.io/)
- Screen 是占据终端尺寸的页面容器，可通过 `push_screen`、`pop_screen`、`dismiss` 管理页面栈和 modal 结果。[Screens](https://textual.textualize.io/guide/screens/)
- 官方布局提供 `Horizontal`、`Vertical`、`Grid`，并支持 CSS/约束布局；样式文档覆盖 background、border、dock、grid、layer、padding、overflow、width/height 等语义属性。[Layout](https://textual.textualize.io/guide/layout/)、[Styles](https://textual.textualize.io/guide/styles/)
- 官方文档和 widget catalog 已覆盖 `Footer`、`ProgressBar`、`RichLog`、`OptionList`、`Tabs`、`Tree`、`DataTable` 等；按键文档支持 bindings、dynamic actions、key/mouse events。[Widgets](https://textual.textualize.io/widgets/)、[Input](https://textual.textualize.io/guide/input/)

**Subtap 结论：** 这是唯一适合直接继续使用的框架。当前 `pyproject.toml` 要求 `textual>=0.80`，锁定版本为 `8.2.8`；升级只需按当前锁定版本验证，不能因为参考项目漂亮就另建框架。[pyproject.toml](../../pyproject.toml)、[uv.lock](../../uv.lock)

### Ratatui

- Ratatui 官方文档明确使用 immediate-mode rendering：每一帧根据应用状态重新绘制，没有永久 widget object；应用负责触发 `draw`。[Rendering](https://ratatui.rs/concepts/rendering/)
- Ratatui 提供 `Block`、`Paragraph`、`List`、`Table`、`Gauge`、`Chart`、`Tabs`、`Scrollbar` 等 widgets，以及 `Length`、`Min`、`Max`、`Ratio`、`Percentage` 等 constraint layout。[Widgets](https://ratatui.rs/concepts/widgets/)、[Layout](https://ratatui.rs/concepts/layout/)
- 官方文档同时指出，render loop、event loop 和大型应用的架构组织由应用负责；常见输入由 crossterm 等外部库承担。[Rendering](https://ratatui.rs/concepts/rendering/)、[Application Patterns](https://ratatui.rs/concepts/application-patterns/)
- Ratatui 官方 README 与许可证为 MIT；官网展示其 Rust、immediate-mode、动态布局和丰富 widgets 能力。[README](https://github.com/ratatui/ratatui/blob/main/README.md)、[LICENSE](https://github.com/ratatui/ratatui/blob/main/LICENSE)、[官网](https://ratatui.rs/)

**Subtap 结论：** 采用 constraint layout、状态驱动重绘和“widget 负责绘制、应用负责状态”的边界意识；拒绝 Rust 迁移。Ratatui 的 immediate mode 不是 Subtap Observer reducer 的替代品，且它不会提供 Textual 的 Screen 栈、Python 组件或现有测试集成。

## Subtap Calm Workbench 的可复用模式

### Token

现有 Subtap 已有 canonical token，不应再创造第二套：

| 语义 | 当前值/来源 | 用法 |
|---|---|---|
| breakpoints | `0 -> -compact`、`80 -> -regular`、`104 -> -wide` | 只改变信息排列，不新增宽屏信息栏 |
| 内容最大宽度 | `104` columns | wide 模式居中，避免超宽终端拉伸信息密度 |
| logo/muted | `#8a8a8a` / `#8b8b92` | 品牌和次要说明，不能承担状态语义 |
| body/accent/link | `#f2f2f2` / `#56d4dd` / `#78a9ff` | 正文、主要进行中状态、可操作链接 |
| Textual semantic colors | `$background`、`$surface`、`$foreground`、`$text-muted`、`$secondary`、`$error` | surface、Footer、详情边框、危险确认 |
| width helpers | `get_display_width`、`truncate_by_width` | 所有 CJK/路径/文件名截断必须经过现有 helper |

来源：`src/subtap/ui/theme.py` 的 `CALM_WORKBENCH_BREAKPOINTS`、`CALM_WORKBENCH_CSS`、`RICH_*` 和宽度 helper。

### 页面级布局

当前 Observer 已给出应保留的骨架：

```text
wide (>=104)
┌──────────────────────────────────────────────────────────────┐
│ status / progress / current-work                             │
├───────────────────────┬──────────────────────────────────────┤
│ pipeline-pane (2fr)   │ activity-pane (3fr)                  │
│ stage-map             │ recent / output / action-status      │
└───────────────────────┴──────────────────────────────────────┘
Footer: l details  f output  d diagnostics  Esc overview  q quit  x stop

compact (<80)
┌──────────────────────────────────────────────────────────────┐
│ status / progress / current-work                             │
│ pipeline-pane                                                │
│ activity-pane                                                │
└──────────────────────────────────────────────────────────────┘
```

- TUIStudio 的三栏职责给出视觉参考；Textual 的 `Grid` 和现有 `2fr/3fr` 给出可直接实现的 Python 形态。
- `L` 进入 `RichLog` 详情，`Esc` 回到概览；`Q` 退出 Observer；`X` 只在任务运行时出现并进入 `ModalScreen` 确认。关闭观察与停止 pipeline 继续保持两个动作。
- 不把“最近字幕”和“完整日志”永久并排；默认页保留稳定状态、当前阶段、最近 2–4 条字幕和输出位置，详情按需展开。

### 组件与反馈

| 需求 | 采用的成熟模式 | Subtap 实现边界 |
|---|---|---|
| 状态/进度 | Textual `Static` + `ProgressBar`；Vue TUI 的 plane 分层 | 以 presentation 更新，不从 UI 反查 pipeline 内部对象 |
| 阶段结构 | TUIStudio 层级树的“可扫描结构” | 用阶段列表和状态符号，不做可编辑树 |
| 事件详情 | Textual `RichLog` 的滚动/行数上限；Vue TUI append-only log | 只展示 reducer 产出的事件；解析错误按现有 fail-fast 约定暴露 |
| 危险操作 | Textual `ModalScreen` | `Y/N/Esc` 明确确认；确认后才向子进程发停止请求 |
| 动效 | Bubble Tea 周边的 spinner/animation 思路 | 只保留 spinner、progress、append feedback；不引入 CSS 动画、渐变背景或运行时 ASCII 字体 |
| 空间反馈 | TUIStudio 的字符网格/选中反馈 | 用终端列宽、状态颜色和当前焦点表达，不复制浏览器 pointer/drag canvas |
| 键盘入口 | TUIStudio command palette + Textual `BINDINGS`/`Footer` | Footer 只显示当前状态可用动作，不手写第二份快捷键文案 |

## 不应直接复用的内容

- **TUIStudio 的 React/TypeScript 组件、Tailwind CSS、Zustand store、Vite 配置、浏览器 file picker、Pointer Event 拖拽和 pixel layout：** 依赖栈与 Subtap 冲突，复制它们会形成第二套 UI runtime。
- **TUIStudio 的 `.tui` JSON 作为 Subtap 任务状态：** 这是设计树格式，不是 pipeline 事件日志、任务恢复或输出元数据格式。
- **Vue TUI 的 Vue components、Node `/cli` entry、DOM/stdout renderer、experimental `TTranscriptView`/`TLogView`：** 即使许可证允许，也需要重写 host、buffer 和 lifecycle；experimental API 不能作为稳定依赖。
- **Bubble Tea/Bubbles/Lip Gloss/Ratatui 的源码或运行时依赖：** Go/Rust 与当前 Python/Textual 架构重叠，且不会消除现有的导航、Observer 和测试边界。
- **把任何参考项目的动画、渐变、全屏装饰边框或固定快捷键照搬：** Subtap 的终端可读性、`NO_COLOR`、CJK 宽度和人工验收优先级更高。

## 许可证与兼容性

| 项目 | 许可证 | 技术栈/运行时 | 对 Subtap 的结论 |
|---|---|---|---|
| TUIStudio | MIT；保留版权与许可证文本 | React 19 / TypeScript / Vite / Zustand / Tailwind；浏览器编辑器 | 法律上可复制小片段，但技术上不兼容；只读视觉模式 |
| Vue TUI | MIT；保留版权与许可证文本 | Vue 3 peer dependency、Node CLI、DOM/stdout renderer；部分功能 experimental | 只读 render-plane、host-boundary 和日志面模式 |
| Bubble Tea | MIT | Go，Elm-style model/update/view，Bubbles/Lip Gloss 分包 | 只读单向状态、组件/样式分责；不迁移 |
| Bubbles / Lip Gloss | MIT | Go 组件与终端样式/布局库 | 不作为 Python 依赖；不复制代码 |
| Textual | MIT | Python；Subtap 当前锁定 Textual 8.2.8 | 继续使用，优先原生 Screen/ModalScreen/Grid/ProgressBar/RichLog/Footer |
| Ratatui | MIT | Rust immediate-mode + external event loop/backend | 只读 constraint layout 和状态重绘；不迁移 |

**许可证结论：** 本次没有发现 GPL 类许可证风险；但 MIT 不是“可以无条件复制”的意思。若未来确实复制任何代码，必须保留版权/许可证声明、记录来源与版本，并重新检查依赖许可证和生成代码质量。本报告推荐的是模式映射，不是代码搬运。

## 风险与缺口

1. **TUIStudio 的导出质量未被本次独立编译验证。** README 宣称支持多个框架，只能证明产品意图，不能证明导出结果可直接进入 Subtap。
2. **Vue TUI 的 experimental 入口存在 API 漂移风险。** 即使将来考虑 Node sidecar，也必须锁定版本并验证包导出契约，当前不需要该复杂度。
3. **官方框架文档描述的是能力边界，不是 Subtap 的成品视觉。** 最终效果仍需人工在 `<80`、`80–103`、`>=104` 列终端验收。
4. **当前工作区已有 `.scratch/` 未跟踪目录。** 本研究没有触碰它；报告之外不应把它当成研究产物。
5. **暂时无法由公开资料确认各项目的生产级可访问性、导出一致性和所有终端兼容矩阵。** 这些信息应通过版本锁定、实际运行和人工验收补足，不应在规划阶段猜测。

## 验证记录

- 官方仓库、README、源码、许可证和官方文档 URL 均已通过可访问性检查；本报告引用的直接 raw/source URL 在检查时返回成功响应。
- TUIStudio、Vue TUI、Bubble Tea、Bubbles、Lip Gloss、Textual、Ratatui 的许可证内容均核对为 MIT。
- 报告只写入本文件；未修改 `src/`、`tests/`、配置、Git、Issues 或其他报告。

## 第一方来源

### 参考项目

- [TUIStudio repository](https://github.com/jalonsogo/tui-studio)
- [TUIStudio README](https://raw.githubusercontent.com/jalonsogo/tui-studio/main/README.md)
- [TUIStudio LICENSE](https://raw.githubusercontent.com/jalonsogo/tui-studio/main/LICENSE)
- [TUIStudio App.tsx](https://raw.githubusercontent.com/jalonsogo/tui-studio/main/src/App.tsx)
- [TUIStudio EditorLayout.tsx](https://raw.githubusercontent.com/jalonsogo/tui-studio/main/src/components/editor/EditorLayout.tsx)
- [TUIStudio Canvas.tsx](https://raw.githubusercontent.com/jalonsogo/tui-studio/main/src/components/editor/Canvas.tsx)
- [TUIStudio ComponentTree.tsx](https://raw.githubusercontent.com/jalonsogo/tui-studio/main/src/components/editor/ComponentTree.tsx)
- [TUIStudio CommandPalette.tsx](https://raw.githubusercontent.com/jalonsogo/tui-studio/main/src/components/editor/CommandPalette.tsx)
- [TUIStudio package.json](https://raw.githubusercontent.com/jalonsogo/tui-studio/main/package.json)
- [Vue TUI repository](https://github.com/Simon-He95/vue-tui)
- [Vue TUI README](https://raw.githubusercontent.com/Simon-He95/vue-tui/main/README.md)
- [Vue TUI license](https://raw.githubusercontent.com/Simon-He95/vue-tui/main/license)
- [Vue TUI package.json](https://raw.githubusercontent.com/Simon-He95/vue-tui/main/package.json)
- [Vue TUI src/index.ts](https://raw.githubusercontent.com/Simon-He95/vue-tui/main/src/index.ts)
- [Vue TUI src/core.ts](https://raw.githubusercontent.com/Simon-He95/vue-tui/main/src/core.ts)

### 官方框架

- [Bubble Tea repository](https://github.com/charmbracelet/bubbletea)
- [Bubble Tea README](https://raw.githubusercontent.com/charmbracelet/bubbletea/main/README.md)
- [Bubble Tea LICENSE](https://raw.githubusercontent.com/charmbracelet/bubbletea/main/LICENSE)
- [Bubbles README](https://raw.githubusercontent.com/charmbracelet/bubbles/main/README.md)
- [Bubbles LICENSE](https://raw.githubusercontent.com/charmbracelet/bubbles/main/LICENSE)
- [Lip Gloss README](https://raw.githubusercontent.com/charmbracelet/lipgloss/main/README.md)
- [Lip Gloss LICENSE](https://raw.githubusercontent.com/charmbracelet/lipgloss/main/LICENSE)
- [Textual official documentation](https://textual.textualize.io/)
- [Textual README](https://raw.githubusercontent.com/Textualize/textual/main/README.md)
- [Textual LICENSE](https://raw.githubusercontent.com/Textualize/textual/main/LICENSE)
- [Textual Screens](https://textual.textualize.io/guide/screens/)
- [Textual Layout](https://textual.textualize.io/guide/layout/)
- [Textual Styles](https://textual.textualize.io/guide/styles/)
- [Textual Input and bindings](https://textual.textualize.io/guide/input/)
- [Ratatui repository](https://github.com/ratatui/ratatui)
- [Ratatui README](https://raw.githubusercontent.com/ratatui/ratatui/main/README.md)
- [Ratatui LICENSE](https://raw.githubusercontent.com/ratatui/ratatui/main/LICENSE)
- [Ratatui Rendering](https://ratatui.rs/concepts/rendering/)
- [Ratatui Widgets](https://ratatui.rs/concepts/widgets/)
- [Ratatui Layout](https://ratatui.rs/concepts/layout/)
- [Ratatui Application Patterns](https://ratatui.rs/concepts/application-patterns/)

### Subtap local context

- `src/subtap/ui/theme.py`
- `src/subtap/ui/observer.py`
- `src/subtap/ui/command_deck.py`
- `docs/research/2026-07-16-tui-task-running-page-patterns.md`
- `docs/research/2026-07-26-tui-redesign-primary-source-review.md`
- `docs/research/2026-07-26-tui-mature-projects-reuse-review.md`
