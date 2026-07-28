# Subtap 成熟 TUI 项目与可复用组件评估

日期：2026-07-26
范围：Subtap 当前 Python、Textual、Apple Silicon macOS TUI
活跃度窗口：2026-01-26 至 2026-07-26

## 结论

不建议推翻 Textual，也不建议把 Posting、Harlequin、Memray 等完整应用作为依赖。Subtap 当前锁定 Textual 8.2.8，最合适的方向是保留框架，替换页面组织与视觉壳层：

1. 用 Textual 原生 `Screen` / `ModalScreen` / `Grid` / Theme / breakpoint 建立单一页面栈。
2. 复用 Posting 的页面壳层、颜色语义和横竖布局切换方式。
3. 复用 Harlequin 的单行控制条排版方式，统一同组控件的高度、间距和对齐。
4. 复用 Memray 的 `.narrow` 响应式布局规则，让标题区和设置区在窄终端自动换行。
5. 保留 Subtap 已有的 macOS 原生文件与目录选择器；`textual-fspicker` 与现有能力重叠，不引入。
6. 仅参考 lazygit、k9s 的返回与退出语义；不复用 Go 代码。

Dolphie 使用 GPL-3.0-or-later，整项排除。Toolong 和 Trogon 已超过六个月没有默认分支提交，不应成为新实现的依赖或骨架。

## 核验方法

- Stars、License、默认分支最新提交日期来自各项目的 GitHub 官方仓库/API，均为 2026-07-26 快照，Stars 后续会变化。
- “近六个月活跃”以默认分支最新提交是否晚于 2026-01-26 判断，不用仓库 `pushed_at` 代替代码提交。
- 只查看官方仓库、官方文档、源码、Release 和 Issue 数据。
- 直接代码复用的最低门槛：许可证允许、Python/Textual 架构相容、依赖不要求替换现有框架。
- 当前 Subtap 基线：Python >=3.10、`textual>=0.80`，`uv.lock` 实际锁定 Textual 8.2.8。
- 本报告完成的是源码、许可证和声明依赖的静态核验；尚未安装候选包，也未执行 Textual 8.2.8 集成测试。

## 总表

| 项目 | Stars | License | 默认分支最新提交 | 近六个月 | 架构 | 直接复用结论 |
|---|---:|---|---|---|---|---|
| [Textual](https://github.com/Textualize/textual/tree/06dbeef4bb70fb718236aa418ed658ef4667a126) | 36,744 | MIT | 2026-07-11 | 是 | Python / Textual | 高：当前已使用，应作为唯一基础框架 |
| [Posting](https://github.com/darrenburns/posting/tree/56703a11513e8e74e681b4f859f31945b71e746f) | 12,190 | Apache-2.0 | 2026-03-25 | 是 | Python / Textual | 中：复用布局与 TCSS 结构，不安装完整应用 |
| [Harlequin](https://github.com/tconbeer/harlequin/tree/a26fd7660c6763240100ea14c2bd673a0eb63536) | 6,284 | MIT | 2026-07-21 | 是 | Python / Textual | 中：复用紧凑控制条和主从布局，不引入其数据组件 |
| [Toolong](https://github.com/Textualize/toolong/tree/5aa22ee878026f46d4d265905c4e1df4d37842ae) | 3,933 | MIT | 2024-04-28 | 否 | Python / Textual | 低：仅参考日志页、查找弹窗与帮助页 |
| [Memray](https://github.com/bloomberg/memray/tree/23f39eed5eacacb1a1b9007c2f90231475d870dc) | 15,178 | Apache-2.0 | 2026-07-22 | 是 | Python / Textual | 中：复用响应式 CSS 和状态表格模式，不引入 Memray |
| [Dolphie](https://github.com/charles-001/dolphie/tree/af4e21fae1518a1b8a22b7811a60514e70f41b73) | 1,188 | GPL-3.0-or-later | 2026-06-04 | 是 | Python / Textual | 禁止：代码、TCSS、素材均不进入 Subtap |
| [Trogon](https://github.com/Textualize/trogon/tree/eaa9e68c403cae6aff0a80957d8876b284fd76b0) | 2,835 | MIT | 2025-03-08 | 否 | Python / Textual / Click | 低：表单概念可参考，不作为依赖 |
| [lazygit](https://github.com/jesseduffield/lazygit/tree/292035709f880f33b9f9c90177f1d2fe63f2bd6a) | 80,735 | MIT | 2026-07-25 | 是 | Go / gocui | 仅交互参考：不能直接复用代码 |
| [k9s](https://github.com/derailed/k9s/tree/436ea2e9f23c5dd2d8e05c3e974220657524ef17) | 34,212 | Apache-2.0 | 2026-07-25 | 是 | Go / tview | 仅交互与品牌区参考：不能直接复用代码 |
| [textual-fspicker](https://github.com/davep/textual-fspicker/tree/e3d8d55baa5f87c8ddb9a23cfcf188957ac087d9) | 101 | MIT | 2026-05-20 | 是 | Python / Textual | 不引入：与现有 macOS 原生文件选择能力重叠 |

## 逐项评估

### 1. Textual：保留并升级使用方式

#### 可迁移模式

- 单一 `App` 管理 `Screen` 栈，二级页用 `push_screen()`，返回用 `pop_screen()`。
- 文件选择、帮助、确认等短流程使用 `ModalScreen`，取消后回到原页面并保留已填设置。
- 设置页使用 `Grid`，同一组 `Select`、`Input`、`Button` 采用相同 row 高度和 `1fr` 列宽。
- 用水平 breakpoint 为根节点添加窄屏 class；TCSS 负责换行，不在 Python 中计算坐标。
- 颜色从 Theme 变量派生，不在每个页面散落硬编码颜色。

#### 可直接复用位置

- [Screens 指南](https://textual.textualize.io/guide/screens/)：`Screen`、`ModalScreen`、push/pop 和回调。
- [Layout 指南](https://textual.textualize.io/guide/layout/)：Grid、Horizontal、Vertical。
- [Theme 指南](https://textual.textualize.io/guide/design/)：语义色与主题注册。
- [breakpoints.py](https://github.com/Textualize/textual/blob/06dbeef4bb70fb718236aa418ed658ef4667a126/examples/breakpoints.py)：官方 class 驱动响应式示例。
- [DirectoryTree](https://textual.textualize.io/widgets/directory_tree/) 及其[源码](https://github.com/Textualize/textual/blob/06dbeef4bb70fb718236aa418ed658ef4667a126/src/textual/widgets/_directory_tree.py)：若不引入文件选择库，可作为自建选择页的底层组件。

#### 依赖与冲突

- 已是 Subtap 运行依赖，无新增框架和打包体积。
- Subtap 目前的主要问题不是 Textual 能力不足，而是多个 `App.run()` / `exit()` 串联出的页面生命周期不具备真正的上一页语义。

#### 适合度

最高。应替换应用组织方式，不替换框架。

### 2. Posting：视觉壳层与主题语义的主要来源

#### 可迁移模式

- 品牌区是普通组件，不把巨型 ASCII 图案和菜单耦合。
- `AppHeader`、`AppBody`、`Footer` 分层，页面主体只保留必要 section。
- `layout-horizontal` / `layout-vertical` class 控制横竖布局，响应变化不重建页面。
- Screen 使用统一背景；边框只给真正需要聚焦提示的 section，避免整页“仪表框标题”。
- Modal 使用半透明遮罩、统一宽度、最大高度、边框和标题颜色。
- Theme 转换为 Textual 原生 Theme，再由 TCSS 使用语义变量。

#### 可直接复用位置

- [AppHeader / AppBody](https://github.com/darrenburns/posting/blob/56703a11513e8e74e681b4f859f31945b71e746f/src/posting/app.py#L93-L109)。
- [应用 compose 与 Footer](https://github.com/darrenburns/posting/blob/56703a11513e8e74e681b4f859f31945b71e746f/src/posting/app.py#L255-L269)。
- [布局 class watcher](https://github.com/darrenburns/posting/blob/56703a11513e8e74e681b4f859f31945b71e746f/src/posting/app.py#L752-L757)。
- [Screen、Modal、section 与横竖布局 TCSS](https://github.com/darrenburns/posting/blob/56703a11513e8e74e681b4f859f31945b71e746f/src/posting/posting.scss#L212-L304)。
- [Textual Theme 转换](https://github.com/darrenburns/posting/blob/56703a11513e8e74e681b4f859f31945b71e746f/src/posting/themes.py#L144-L242)。

#### 依赖与冲突

- Posting 锁定 `textual[syntax]==6.1.0`，Subtap 锁定 8.2.8；不能把 Posting 安装成运行依赖。
- Posting 还依赖 HTTP、autocomplete、配置等与 Subtap 无关的组件，完整引入会造成明显功能重叠和体积增长。
- Apache-2.0 允许复用，但若直接复制代码或 TCSS，必须保留许可证和 NOTICE 要求，并标明修改。更合适的是复用结构和语义，按 Subtap 组件重新实现。

#### 适合度

高，作为视觉系统和页面壳层参考；不作为组件包。

### 3. Harlequin：单行控件和工整排版的主要来源

#### 可迁移模式

- 左侧导航 / 右侧主面板 / 底部 Footer 的稳定主从结构。
- 同一任务上下文中的操作控件放入一个 `Horizontal`，而不是逐项占满整行。
- 控制条固定一行高，输入框和按钮去除多余边框，主要动作使用主题主色。
- 次要控制组宽度 `auto`，主要控制组 `1fr` 并右对齐。
- focus、disabled、invalid 都通过同一组主题变量表达。

#### 可直接复用位置

- [主从布局 compose](https://github.com/tconbeer/harlequin/blob/a26fd7660c6763240100ea14c2bd673a0eb63536/src/harlequin/app.py#L246-L275)。
- [RunQueryBar 单行控件组合](https://github.com/tconbeer/harlequin/blob/a26fd7660c6763240100ea14c2bd673a0eb63536/src/harlequin/components/run_query_bar.py#L13-L64)。
- [RunQueryBar 高度、宽度、对齐和按钮样式](https://github.com/tconbeer/harlequin/blob/a26fd7660c6763240100ea14c2bd673a0eb63536/src/harlequin/app.tcss#L167-L220)。
- [应用级 focus / disabled / tree 颜色语义](https://github.com/tconbeer/harlequin/blob/a26fd7660c6763240100ea14c2bd673a0eb63536/src/harlequin/app.tcss#L1-L105)。

#### 依赖与冲突

- Harlequin 锁定 Textual 6.4.0，并依赖 `textual-fastdatatable`、`textual-textarea`；完整引入与 Subtap 8.2.8 基线冲突。
- 数据目录、SQL 编辑器和结果表格与 Subtap 无关。
- MIT 允许移植单行控制条结构；复制代码时需保留版权与许可证声明。

#### 适合度

高，适合解决热词、参考文稿、字幕字数、输出目录等设置控件过高、过散、对不齐的问题。

### 4. Toolong：Observe 页的交互参考，不作为依赖

#### 可迁移模式

- 多任务日志使用 `TabbedContent`，只有一个任务时隐藏 Tabs。
- 查找条是一个横向轻量控件，`Esc` 只关闭查找，不退出应用。
- 跳转行号使用 `ModalScreen`，帮助页也是可关闭的 `ModalScreen`。
- Help 使用 `VerticalScroll + Markdown + Footer`，不另起一个 App。

#### 可直接复用位置

- [LogScreen、TabbedContent、Help screen](https://github.com/Textualize/toolong/blob/5aa22ee878026f46d4d265905c4e1df4d37842ae/src/toolong/ui.py#L22-L75)。
- [单行 FindDialog 与 Esc 关闭](https://github.com/Textualize/toolong/blob/5aa22ee878026f46d4d265905c4e1df4d37842ae/src/toolong/find_dialog.py#L26-L65)。
- [GotoScreen](https://github.com/Textualize/toolong/blob/5aa22ee878026f46d4d265905c4e1df4d37842ae/src/toolong/goto_screen.py#L15-L47)。
- [HelpScreen](https://github.com/Textualize/toolong/blob/5aa22ee878026f46d4d265905c4e1df4d37842ae/src/toolong/help.py#L135-L173)。

#### 依赖与冲突

- 默认分支最后提交是 2024-04-28，最新 Release 1.4.0 发布于 2024-03-02。
- 依赖 Textual `^0.58.0`，与当前 8.2.8 存在较大 API 跨度。
- 不能直接复制整页；只应把 Tabs、查找、跳转、帮助的交互模式用当前 Textual API重写。

#### 适合度

中低。适合 Observe 页设计参考，不适合作为新依赖。

### 5. Memray：响应式状态页的主要来源

#### 可迁移模式

- Header 是独立 Widget，业务状态、元数据、主表格、Footer 分层。
- 宽屏 `#header_container` 横向，`.narrow` 自动切换纵向。
- Header 元数据使用两列 Grid；窄屏调整高度、边框和布局，不截断内容。
- DataTable 使用固定表头、斑马纹和稳定排序，适合 Observe / Models / Doctor。
- Footer 的快捷键描述能随状态变化，例如 Pause / Unpause。

#### 可直接复用位置

- [Header 组件](https://github.com/bloomberg/memray/blob/23f39eed5eacacb1a1b9007c2f90231475d870dc/src/memray/reporters/tui.py#L466-L512)。
- [TUI Screen、bindings、compose](https://github.com/bloomberg/memray/blob/23f39eed5eacacb1a1b9007c2f90231475d870dc/src/memray/reporters/tui.py#L514-L646)。
- [宽屏 / narrow Header 和 Grid TCSS](https://github.com/bloomberg/memray/blob/23f39eed5eacacb1a1b9007c2f90231475d870dc/src/memray/reporters/tui.css#L16-L90)。

#### 依赖与冲突

- Memray 本体包含本地性能分析和编译组件，作为运行依赖完全不合理。
- TUI 内部使用 `memray.reporters._textual_hacks`，这些私有兼容代码不能移植。
- Apache-2.0 允许移植公开布局代码，但需履行许可证要求。
- 其 `q,esc` 都退出的绑定不适合 Subtap；只复用响应式布局，不复用退出语义。

#### 适合度

高，适合响应式 Header、状态卡和表格；不适合整体依赖。

### 6. Dolphie：许可证硬性排除

#### 可观察模式

- 数据密集型仪表、命令面板、状态颜色和多区域布局具有视觉参考价值。
- 相关源码集中在 [`dolphie/App.py`](https://github.com/charles-001/dolphie/blob/af4e21fae1518a1b8a22b7811a60514e70f41b73/dolphie/App.py)、[`CommandPalette.py`](https://github.com/charles-001/dolphie/blob/af4e21fae1518a1b8a22b7811a60514e70f41b73/dolphie/Modules/CommandPalette.py) 和 [`CommandScreen.py`](https://github.com/charles-001/dolphie/blob/af4e21fae1518a1b8a22b7811a60514e70f41b73/dolphie/Widgets/CommandScreen.py)。

#### 排除原因

- [LICENSE](https://github.com/charles-001/dolphie/blob/af4e21fae1518a1b8a22b7811a60514e70f41b73/LICENSE) 与 `pyproject.toml` 均声明 GPL-3.0-or-later。
- Subtap 的商业发布边界不接受 GPL 类风险。
- 禁止复制代码、TCSS、图标、文案和素材；也不将其作为实现模板。

#### 适合度

不适合，整项拒绝。

### 7. Trogon：表单思想可参考，但维护状态不合格

#### 可迁移模式

- 左侧命令树、右侧可滚动参数表单、底部命令预览。
- Arguments / Options 分组，参数控件有统一 label、help text、focus 样式。
- 多选项封装为独立 Widget，方向键在选项内移动。

#### 可直接复用位置

- [CommandBuilder 页面](https://github.com/Textualize/trogon/blob/eaa9e68c403cae6aff0a80957d8876b284fd76b0/trogon/trogon.py#L42-L141)。
- [整体 SCSS](https://github.com/Textualize/trogon/blob/eaa9e68c403cae6aff0a80957d8876b284fd76b0/trogon/trogon.scss)。
- [Form 分组和筛选](https://github.com/Textualize/trogon/blob/eaa9e68c403cae6aff0a80957d8876b284fd76b0/trogon/widgets/form.py#L99-L148)。
- [MultipleChoice](https://github.com/Textualize/trogon/blob/eaa9e68c403cae6aff0a80957d8876b284fd76b0/trogon/widgets/multiple_choice.py#L15-L96)。
- [参数到 Input / Select / Checkbox 的映射](https://github.com/Textualize/trogon/blob/eaa9e68c403cae6aff0a80957d8876b284fd76b0/trogon/widgets/parameter_controls.py#L105-L258)。

#### 依赖与冲突

- 默认分支最后提交是 2025-03-08，最新 Release 0.6.0 发布于 2024-10-02，近六个月不活跃。
- 核心用途是从 Click schema 自动生成 TUI；Subtap 已有专用页面和业务状态，完整引入会造成架构和功能重叠。
- 虽声明 `textual>=2.1.2`，但长期未跟随 Textual 8.x 验证。

#### 适合度

低。表单分组思想可吸收，代码不应成为当前改造基础。

### 8. lazygit：返回 / 退出语义参考

#### 可迁移模式

- `Esc` 是取消、关闭、回退；不会在任意层级直接终止整个工具。
- `q` / `Ctrl+C` 是明确的全局退出动作。
- 快捷键提示保持短、稳定、可预测。

#### 参考位置

- [全局 Cancel / Quit bindings](https://github.com/jesseduffield/lazygit/blob/292035709f880f33b9f9c90177f1d2fe63f2bd6a/docs/keybindings/Keybindings_en.md#L20-L31)。
- [Secondary / Back bindings](https://github.com/jesseduffield/lazygit/blob/292035709f880f33b9f9c90177f1d2fe63f2bd6a/docs/keybindings/Keybindings_en.md#L220-L228)。

#### 依赖与冲突

- Go / gocui，与 Python / Textual 完全不同。
- 禁止直接复制控制器、布局和渲染代码；只采用键位语义。

#### 适合度

高交互参考，零代码复用。

### 9. k9s：品牌区组件化和导航语义参考

#### 可迁移模式

- Logo 是独立组件，尺寸固定，颜色来自皮肤主题，状态信息单独占一行。
- `Esc` 返回上一视图，`q` / `Ctrl+C` 退出。
- 品牌区在窄终端应有简化版本，不让 Logo 挤压主菜单。

#### 参考位置

- [Logo 组件](https://github.com/derailed/k9s/blob/436ea2e9f23c5dd2d8e05c3e974220657524ef17/internal/ui/logo.go#L15-L40)。
- [Navigation / Exit 快捷键](https://github.com/derailed/k9s/blob/436ea2e9f23c5dd2d8e05c3e974220657524ef17/README.md#L385-L396)。

#### 依赖与冲突

- Go / tview，与 Subtap 架构不相容。
- K9s Logo 属于其品牌资产，不能复制；只能采用“品牌组件 + 响应式简化 + 主题色”的结构。
- 不应再引入 Figlet 一类运行时字体依赖。Subtap 应保存经过人工验收的固定 `SUBTAP` 字样，并提供纯文本 fallback。

#### 适合度

高视觉与导航参考，零代码复用。

### 10. textual-fspicker：静态兼容，但不引入

#### 已核验能力

- `FileOpen`：选择单个输入媒体文件。
- `SelectDirectory`：选择输出目录。
- `FileSystemPickerScreen(ModalScreen[Path | None])`：选择结果是 `Path`，取消是 `None`。
- `Esc` 已定义为 `dismiss(None)`，返回设置页且不破坏已填内容。
- 文件过滤、路径输入、隐藏文件切换、打开/取消按钮已包含，不需要 Subtap 自建文件树。

#### 可直接复用位置

- [ModalScreen 基类、统一按钮行、Esc 取消](https://github.com/davep/textual-fspicker/blob/e3d8d55baa5f87c8ddb9a23cfcf188957ac087d9/src/textual_fspicker/base_dialog.py#L44-L198)。
- [FileOpen](https://github.com/davep/textual-fspicker/blob/e3d8d55baa5f87c8ddb9a23cfcf188957ac087d9/src/textual_fspicker/file_open.py#L19-L72)。
- [文件过滤、路径输入与选择同步](https://github.com/davep/textual-fspicker/blob/e3d8d55baa5f87c8ddb9a23cfcf188957ac087d9/src/textual_fspicker/file_dialog.py#L29-L154)。
- [SelectDirectory](https://github.com/davep/textual-fspicker/blob/e3d8d55baa5f87c8ddb9a23cfcf188957ac087d9/src/textual_fspicker/select_directory.py#L24-L93)。
- [1.0.1 Release](https://github.com/davep/textual-fspicker/releases/tag/v1.0.1)，发布于 2026-05-20。

#### 健康度与依赖

- Stars 只有 101，未达到通用项目 1k 门槛，但它是单一用途的小型 Textual 组件。
- 默认分支在 2026-05-20 有提交；1.0.1 同日发布。
- 最近 Issue #89 在约 34 分钟后得到响应并于当天关闭；#91 在约 6 天内关闭。小众库的维护响应可接受。
- MIT License。
- 要求 Python >=3.10、`textual>=1.0.0`，声明的版本约束与 Subtap Python >=3.10、Textual 8.2.8 不冲突；实际运行兼容性仍需用最小原型和测试确认。
- 不要求替换框架，但与 `textual_run_setup.py` 已有的 macOS 原生文件与目录选择能力重叠。

#### 适合度

不进入实现。当前设置页已经先渲染，再由页面内按钮调用 macOS 原生选择器；取消或改选都会返回原设置页。新增依赖不会补足能力，只会制造第二套文件选择交互。

## License 与架构硬门槛

### 可进入实现

- MIT：Textual、Harlequin、Toolong、Trogon、lazygit、textual-fspicker。许可证允许不等于应当引入。
- Apache-2.0：Posting、Memray、k9s。复制代码时必须处理许可证、版权和 NOTICE。

### 必须排除

- Dolphie：GPL-3.0-or-later，禁止直接或改写后复用代码、样式和素材。
- lazygit、k9s：许可证允许，但更换到 Go UI 代码会破坏 Python/Textual 架构；只取交互原则。
- Toolong、Trogon：超过六个月不活跃且基于旧 Textual 时代，不作为运行依赖。
- Posting、Harlequin、Memray：完整应用依赖与 Subtap 功能重叠；不安装，只迁移经过筛选的布局模式。
- textual-fspicker：与 Subtap 已有 macOS 原生文件/目录选择器功能重叠；停止引入。

## 对 Subtap 七项需求的对应方案

| 需求 | 成熟方案来源 | 决定 |
|---|---|---|
| Logo 与说明位置 | k9s 的独立 Logo 组件、Posting 的普通 Header | Logo 独立组件；说明固定在 Logo 下；宽屏显示固定 `SUBTAP` 字样，窄屏退化为纯文本 `SUBTAP`；不引入运行时 ASCII 字体库 |
| 文件选择进入仪表 | Textual Screen stack、现有 macOS 原生选择器 | 先渲染设置页，再由页面内按钮打开选择器；取消或改选都回原设置页 |
| 多选项同一行、尺寸一致 | Harlequin RunQueryBar、Textual Grid | 每组控件一个 Grid/Horizontal；统一 row 高度、`1fr` 列宽、间距和 focus 样式 |
| 去掉顶部框标题 | Posting Screen / section TCSS | Screen 无整页 border；只在需要聚焦的局部 section 使用弱边框；页面标题是普通 Label |
| 更成熟的颜色与排版 | Posting Theme、Memray responsive CSS | 使用背景、surface、primary、muted、success、warning、error 七类语义色；窄屏 class 自动换行 |
| Back 与 Quit 分离 | Textual Screen stack、lazygit、k9s | `Esc` 关闭 Modal 或 `pop_screen()`；`Q` / `Ctrl+C` 才 `exit()` |
| 二级页不再工程化 | Posting 壳层、Harlequin 控制条、Memray 状态区 | 统一 Header / Body / Footer，减少边框、减少全宽输入框、保持密度与对齐 |

## 唯一推荐组合

采用以下固定组合，不再并列多个候选：

> **Subtap Calm Workbench：Textual 8.2.8 原生页面栈、Footer、控件与响应式能力 + Posting 的页面壳层和主题语义 + Harlequin 的单行控制条 + Memray 的 narrow 状态布局。**

执行边界：

- 本轮 UI 重设计不新增第三方运行依赖，也不直接复制第三方源码。
- Posting、Harlequin、Memray 只作为布局、TCSS 与信息密度参考，不安装完整项目。
- Toolong 仅用于 Observe 页的 Tabs / Find / Help 交互设计，不复制旧 API 代码。
- lazygit、k9s 仅确定 `Esc=Back`、`Q=Quit` 及 Logo 组件化原则。
- Dolphie、Trogon 不进入实现。
- 不换语言、不换框架、不新增 Figlet/ASCII 字体库、不重写 Textual 已有的 Screen、ModalScreen、Footer、Grid、Theme、ProgressBar、RichLog、OptionList 能力。

这套组合能覆盖当前全部问题，并把依赖、许可证和版本漂移风险降为零。第三方源码只有在 Textual 原生能力被实际证明不足后，才重新进入复用评估。

## GPT-5.6 Sol 复审与本地采用决定

2026-07-26 使用 ChatGPT Web 的 GPT-5.6 Sol High 完成文件级复审；Pro 未在当前账号模型选择器中提供，因此按 Skill 路由降级到 High。已核验返回标记 `GPT56_SOL_PRO_RESULT_20260726_TUI_REUSE`。

采用：

- 方案名称固定为 **Subtap Calm Workbench**。
- 一个页面壳层、一个语义主题、一个响应式规则、一个任务呈现模型；优先使用 Textual 原生控件。
- `HORIZONTAL_BREAKPOINTS` 固定为 compact `<80`、regular `80–103`、wide `>=104`；内容最大宽度 104 列。
- `Footer` 读取当前页面 bindings，删除手写快捷键提示。
- 运行页只显示一个主进度条；阶段列表来自真实 `pipeline_plan`。
- `pipeline -> run.log.jsonl -> reducer -> task presentation -> Observer UI` 边界保持不变。

修正：

- `textual>=0.80` 不是可靠的源码兼容契约。未确定并测试 Textual API 最低版本前，Posting、Harlequin、Toolong 都不能作为代码捐赠源。
- 现有设置页通过 `_pending_command` 把同一按钮的第二次点击变成启动确认，语义不稳定；改为独立的任务复核 Modal。
- 首页应是任务启动器，不是 Logo 展示页；固定 `SUBTAP` 字样保留为紧凑品牌标识，不建立宽屏 ASCII Logo 子系统。

实施顺序：

1. 固定 Textual 版本契约、语义状态和键盘语义。
2. 建立共享主题、页面壳层、Footer、focus 和 breakpoint。
3. 用 Models、Glossary、Doctor 验证完整页面迁移。
4. 整页迁移 Setup，并以任务复核 Modal 替换二次点击确认。
5. 建立只读任务呈现模型，整页迁移 Observer。
6. 统一 Completed、Failed、History。
7. 最后迁移 Home，再删除旧 CSS、手写 Footer、重复颜色和 resize 补丁。

验收基线：

- Home、Setup、Running、Completed、Failed、History 各覆盖 `60×56`、`90×56`、`120×56`，共 18 个必测视觉状态。
- Setup 与 Running 增加 `90×24` 低高度测试。
- 60 列无横向滚动、主操作截断或 CJK 断裂；120 列内容不超过 104 列。
- `Esc` 只返回一级，`Q` 退出或从 Observer 脱离，`X` 只在运行中出现并必须确认。
- 无颜色时仍可区分 focus、Running、Completed、Failed。
