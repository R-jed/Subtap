# Subtap TUI 设计规格

基于 Mole 项目的 TUI 设计深度分析，为 Subtap 项目规划的终端 UI 设计方案。

---

## 一、Mole TUI 设计分析

### 1. 颜色体系

Mole 使用 8 色 ANSI 方案，每种颜色有明确的语义：

| 颜色 | ANSI 码 | 语义 | Mole 用途 |
|------|---------|------|----------|
| GREEN | `\033[0;32m` | 成功/正面 | ✓ 成功消息、KB 级大小 |
| BLUE | `\033[1;34m` | 信息/链接 | 信息提示、菜单前缀、标题 |
| CYAN | `\033[0;36m` | 当前选中/高亮 | ➤ 选中菜单项 |
| YELLOW | `\033[0;33m` | 警告/错误 | ☻ 错误图标、MB 级大小 |
| PURPLE | `\033[0;35m` | 区域标题 | ➤ 段落标题 |
| PURPLE_BOLD | `\033[1;35m` | 一级标题 | 区块头部、菜单标题 |
| RED | `\033[0;31m` | 高严重度 | GB 级大小警告 |
| GRAY | `\033[0;90m` | 弱化/装饰 | 控制提示栏、调试信息 |

**关键设计**：`NO_COLOR` 环境变量支持（https://no-color.org），任何非空值禁用所有 ANSI。

### 2. 图标系统

```python
ICON_CONFIRM = "◎"   # 确认提示
ICON_ADMIN   = "⚙"   # 管理/设置
ICON_SUCCESS = "✓"   # 成功完成
ICON_ERROR   = "☻"   # 错误（笑脸符号，非标准）
ICON_WARNING = "◎"   # 警告
ICON_EMPTY   = "○"   # 空状态/未选中
ICON_SOLID   = "●"   # 实心/已选中
ICON_LIST    = "•"   # 列表项
ICON_SUBLIST = "↳"   # 子列表项
ICON_ARROW   = "➤"   # 箭头（选中/标题前缀）
ICON_DRY_RUN = "→"   # 干运行指示
ICON_REVIEW  = "☞"   # 审查模式
ICON_NAV_UP  = "↑"   # 向上导航
ICON_NAV_DOWN= "↓"   # 向下导航
ICON_INFO    = "ℹ"   # 信息提示
```

### 3. 主菜单设计

**布局结构**（从上到下）：
```
┌──────────────────────────────────────┐
│  (空行)                               │
│  __  __       _                       │
│ |  \/  | ___ | | ___                  │
│ | |\/| |/ _ \| |/ _ \  https://mole.fit│
│ | |  | | (_) | |  __/                 │
│ |_|  |_|\___/|_|\___|  Deep clean... │
│  (空行)                               │
│  (更新消息，可选)                       │
│  (空行)                               │
│  ➤ 1. Clean        Free up disk space │
│    2. Uninstall    Remove apps...     │
│    3. Optimize     Refresh caches...  │
│    4. Analyze      Explore disk...    │
│    5. Status       Monitor system...  │
│  (空行)                               │
│  ↑↓ | Enter | M More | V Version | Q Quit│
│  (空行)                               │
│  (下方空白由 \033[J 清除)              │
└──────────────────────────────────────┘
```

**渲染技术**：
- `printf '\033[H'` — 光标归位（非 clear_screen，避免闪烁）
- `printf '\r\033[2K'` — 逐行清除+重写（避免全屏刷新闪烁）
- `printf '\033[J'` — 清除光标以下所有内容（防止残留）
- `hide_cursor` / `show_cursor` — 交互时隐藏光标

**菜单选项渲染**：
```python
def show_menu_option(number, text, selected):
    if selected:
        return f"{CYAN}➤ {number}. {text}{NC}"
    else:
        return f"  {number}. {text}"
```

**控制提示栏**：
- 灰色弱化显示
- 条件渲染（TouchID 未配置时显示 T 键，有更新时显示 U 键）
- 仅在 TTY 交互模式下渲染（`[[ -t 0 ]]` 检测）

### 4. 键盘交互系统

**双模式设计**：

```
MOLE_READ_KEY_FORCE_CHAR
    ┌─────────┴─────────┐
未设置（导航模式）    设置为 1（过滤模式）
    │                      │
vim 键位 + 功能键       所有可打印字符
j/k/h/l/gg/G           → CHAR:$key
q/R/m/v/u/t            → 用于文本过滤
方向键(ESC序列)         方向键(ESC序列)
Ctrl+C → QUIT          Ctrl+C → QUIT
```

**ESC 序列解析**：
- CSI 序列：`ESC [ A/B/C/D` → 方向键（每步 1 秒超时）
- SS3 序列：`ESC O A/B/C/D` → 方向键（application mode 兼容）
- `ESC [ 3 ~` → Delete 键
- 单独 ESC → QUIT（退出过滤模式）

**gg 组合键**：
- 收到第一个 `g` 后，300ms 超时等待第二个字符
- 300ms 内收到 `g` → `TOP`（跳转顶部）
- 超时 → `OTHER`（丢弃，避免误触发）

**drain_pending_input 防抖**：
- 默认 10ms 超时排空缓冲区
- 安全阀：最多排空 100 个字符
- 防止鼠标滚轮等快速输入导致菜单跳跃

**信号处理三层保护**：
1. `trap handle_interrupt INT TERM` — 捕获 Ctrl+C/SIGTERM
2. `trap cleanup EXIT` — 任何退出都恢复终端状态
3. `_menu_restore_traps()` — 退出时恢复调用方 trap 链

### 5. Spinner/进度系统

**协作式 Spinner 架构**：
```
主进程                    子进程
  │                        │
  ├─ start_inline_spinner ─┤─→ 后台循环输出 spinner 字符
  │   创建 stop_file       │
  │                        │
  ├─ (执行工作)            ├─ 检查 stop_file 是否存在
  │                        │
  ├─ stop_inline_spinner ──┤─→ touch stop_file → 子进程退出
  │   等待子进程退出       │
  │   清除行内容           │
```

**关键设计**：
- 协作式停止（非信号）：通过 `stop_file` 文件通信
- 输出到 stderr：不干扰 stdout 的数据流
- 行级清除：`printf "\r\033[2K"` 清除整行
- 消息截断：根据终端宽度自动截断过长消息（预留 8 字符给前缀）
- 非 TTY 降级：管道模式下输出纯文本 `| message`
- 唯一文件名：`mole_spinner_$$RANDOM.stop`（PID + 随机数）

**区段追踪系统**：
```python
start_section("Clean")    # 设置 TRACK_SECTION=1, SECTION_ACTIVITY=0
  note_activity()         # 标记有活动
  log_success("...")      # 显示结果
end_section()             # 如果无活动，显示 "Nothing to tidy"
```

**进度更新（节流）**：
```python
update_progress_if_needed(completed, total, last_update_var, interval=2)
# 基于时间节流，默认 2 秒间隔
# 使用 eval 间接引用变量（bash 3.2 兼容）
```

### 6. 日志/输出系统

**日志三层架构**：

| 层级 | 输出目标 | 格式 | 控制变量 |
|------|---------|------|---------|
| 用户可见 | stdout/stderr | 带颜色+图标 | - |
| 操作日志 | `~/Library/Logs/mole/operations.log` | 纯文本+时间戳 | `MO_NO_OPLOG=1` 禁用 |
| 调试日志 | `~/Library/Logs/mole/mole_debug_session.log` | 仅 `MO_DEBUG=1` | `MO_DEBUG=1` 启用 |

**日志格式**：
```
用户可见:   ✓ Removed 150 items (2.5GB)
操作日志:   [2026-07-04 14:30:00] [clean] REMOVED /path/to/file (15.2MB)
调试日志:   [2026-07-04 14:30:00] DEBUG: PERF [File Scan] 1.234s
```

**日志轮转**：主日志 1MB / 操作日志 5MB，自动 `.old` 备份。

**摘要块渲染**：
```
======================================================================
Mole Cleanup Summary
  ✓ Removed 150 items (2.5GB)
  ○ Skipped 20 items (whitelist)
======================================================================
```

**按大小着色**：
- GB → 红色（警告）
- MB → 黄色（关注）
- KB → 绿色（安全）
- B → 灰色（忽略）

**超链接支持**：OSC 8 `file://` 协议，终端可点击路径。

### 7. CJK 宽度计算

```python
def get_display_width(str):
    char_count = len(str)        # UTF-8 字符数 (LC_ALL=en_US.UTF-8)
    byte_count = len(str.encode('utf-8'))  # 字节数
    extra_bytes = byte_count - char_count
    width = char_count + extra_bytes // 2
    # "中" (1 char, 3 bytes) → 1 + 1 = 2 ✅
    # "A" (1 char, 1 byte) → 1 + 0 = 1 ✅
```

---

## 二、Subtap TUI 设计方案

### 技术选型

| 维度 | 选择 | 理由 |
|------|------|------|
| 框架 | **Rich** (已集成) | 功能强大，内置 CJK/进度条/表格 |
| 交互 | **rich.prompt** + 自定义键盘 | 菜单选择需要自定义 |
| 布局 | **rich.layout** + **rich.live** | 实时更新 pipeline 进度 |

### 颜色映射（Rich → Mole 语义）

```python
# src/subtap/ui/theme.py
THEME = {
    "success":   "green",      # ✓ 成功
    "info":      "blue",       # 信息提示
    "active":    "cyan",       # ➤ 选中项
    "warning":   "yellow",     # ⚠ 警告
    "heading":   "magenta",    # ➤ 区域标题
    "error":     "red",        # ✗ 错误
    "muted":     "dim",        # 控制提示
    "accent":    "bold cyan",  # 品牌高亮
}
```

### 主菜单设计

```
╭─ Subtap ─────────────────────────────────╮
│                                          │
│  ➤ 1. run      运行完整字幕生成流程       │
│    2. clean     仅运行文本清洗阶段        │
│    3. export    仅运行字幕导出阶段        │
│    4. config    查看/修改配置             │
│    5. models    管理模型                  │
│                                          │
│  ↑↓ 导航  Enter 确认  Q 退出             │
│                                          │
╰──────────────────────────────────────────╯
```

### Pipeline 进度设计

```
╭─ Pipeline ───────────────────────────────╮
│                                          │
│  ✓ 音频标准化          0.3s              │
│  ✓ 音频切段            0.2s              │
│  ⠙ 语音识别            14.7s (8/14 段)   │
│  · 文本清洗                             │
│  · 智能断句                             │
│  · 时间轴对齐                           │
│  · 字幕导出                             │
│                                          │
╰──────────────────────────────────────────╯
```

**状态图标**：
- `✓` — 完成（绿色）
- `⠙` — 进行中（spinner，蓝色）
- `·` — 等待（灰色）
- `✗` — 失败（红色）

### 交互流程

```
subtap run input.mp3
  │
  ├─ 显示 Pipeline 进度 (rich.live 实时更新)
  │   ├─ 每个 stage 显示 spinner + 耗时
  │   └─ 完成后显示汇总表
  │
  ├─ 错误处理
  │   ├─ 显示错误详情（红色）
  │   └─ 提示重试选项
  │
  └─ 完成
      ├─ 显示输出路径
      └─ 显示性能指标
```

### 实现计划

| 阶段 | 内容 | 文件 |
|------|------|------|
| 1 | 主菜单交互 | `src/subtap/ui/menu.py` |
| 2 | Pipeline 进度优化 | `src/subtap/ui/tui.py` (已有) |
| 3 | 主题/颜色系统 | `src/subtap/ui/theme.py` |
| 4 | 错误展示优化 | `src/subtap/ui/error.py` |

---

## 三、Mole TUI 设计要点总结

1. **ANSI 转义序列控制**：全程使用 `\033[H`（Home）、`\033[2K`（清行）、`\033[J`（清屏尾）实现无闪烁原地重绘。
2. **颜色体系**：绿色（品牌）、青色（选中高亮）、紫色（章节标题）、灰色（控制提示）、蓝色（链接）、黄色（警告）、红色（大体积）。
3. **CJK 宽度处理**：`get_display_width` 函数处理中日韩字符宽度（占 2 列）。
4. **终端自适应**：动态检测终端宽度/高度，控制栏自动换行，分页数随终端高度调整。
5. **输入处理**：`read_key` 统一解析键盘输入（方向键 ESC 序列、vim 键位 j/k/h/l/G/gg、Ctrl+C 等），返回语义化字符串。
6. **进程模型**：主菜单用 `exec` 替换为子命令进程，子命令结束后没有返回菜单（需要重新运行 `mo`）。
7. **协作式 Spinner**：通过 stop_file 文件通信，避免信号处理复杂性，防止僵尸进程。
8. **三层日志**：用户可见（stdout/stderr）、操作日志（可禁用）、调试日志（MO_DEBUG=1）。
9. **NO_COLOR 支持**：遵循 https://no-color.org 规范，任何非空值禁用所有 ANSI。
10. **超链接支持**：OSC 8 `file://` 协议，终端可点击路径。
