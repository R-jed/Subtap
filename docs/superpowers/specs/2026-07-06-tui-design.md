# Subtap TUI 设计规格

基于 Mole 项目的 TUI 设计分析，为 Subtap 项目规划的终端 UI 设计方案。

## 参考项目：Mole TUI 设计分析

### 1. 颜色体系

Mole 使用 8 色 ANSI 方案，每种颜色有明确的语义：

| 颜色 | ANSI 码 | 语义 | Mole 用途 |
|------|---------|------|----------|
| GREEN | `\033[0;32m` | 成功/正面 | ✓ 成功消息、KB 级大小 |
| BLUE | `\033[1;34m` | 信息/链接 | 信息提示、菜单前缀 |
| CYAN | `\033[0;36m` | 当前选中/高亮 | ➤ 选中菜单项 |
| YELLOW | `\033[0;33m` | 警告/错误 | ☻ 错误、MB 级大小 |
| PURPLE | `\033[0;35m` | 区域标题 | ➤ 段落标题 |
| PURPLE_BOLD | `\033[1;35m` | 一级标题 | 区块头部 |
| RED | `\033[0;31m` | 高严重度 | GB 级大小 |
| GRAY | `\033[0;90m` | 弱化/装饰 | 控制提示、调试信息 |

**关键设计**：`NO_COLOR` 环境变量支持（https://no-color.org），任何非空值禁用 ANSI。

### 2. 图标系统

Mole 定义了一套语义化图标：

```
确认/选择:  ◎
管理/设置:  ⚙
成功:       ✓
错误:       ☻
警告:       ◎
空心:       ○
实心:       ●
列表:       •
子列表:     ↳
箭头:       ➤
干运行:     →
审查:       ☞
导航上:     ↑
导航下:     ↓
信息:       ℹ
```

### 3. 主菜单设计

```
┌──────────────────────────────────────┐
│                                      │
│  [品牌 Banner - ASCII Art]           │
│                                      │
│                                      │
│  ➤ 1. Clean        Free up disk space│
│    2. Uninstall    Remove apps       │
│    3. Optimize     Refresh caches    │
│    4. Analyze      Explore disk usage│
│    5. Status       Monitor health    │
│                                      │
│  ↑↓ | Enter | M More | V Version    │
│       | T TouchID | Q Quit           │
│                                      │
└──────────────────────────────────────┘
```

**渲染技术**：
- `printf '\033[H'` — 光标归位（非 clear_screen，避免闪烁）
- `printf '\r\033[2K'` — 逐行清除+重写（避免全屏刷新闪烁）
- `printf '\033[J'` — 清除光标以下所有内容（防止残留）
- `hide_cursor` / `show_cursor` — 交互时隐藏光标

### 4. 菜单选项渲染

```bash
show_menu_option() {
    local number="$1"
    local text="$2"
    local selected="$3"

    if [[ "$selected" == "true" ]]; then
        echo -e "${CYAN}${ICON_ARROW} $number. $text${NC}"
    else
        echo "  $number. $text"
    fi
}
```

**设计要点**：
- 选中项：CYAN + ➤ 箭头前缀
- 未选中项：纯文本，2 空格缩进
- 编号+文本对齐（固定宽度）

### 5. 键盘交互

Mole 支持两套键位：

**方向键模式**：
- `↑/↓` — 上下导航
- `Enter` — 确认选择
- `Q` — 退出

**Vim 模式**：
- `j/k` — 上下导航
- `h/l` — 左右导航
- `gg/G` — 跳到顶部/底部

**功能键**：
- `M` — 更多信息
- `V` — 版本信息
- `U` — 更新
- `T` — TouchID 配置
- `R` — 重试

**底层实现**：
- `read -r -s -n 1` — 读取单字符
- ESC 序列解析：`ESC [ A/B/C/D` → 方向键
- 超时处理：`read -t 1` 防止阻塞

### 6. Spinner 设计

Mole 的 spinner 是最精妙的 TUI 组件：

```
  | Scanning items... 42/100
```

**架构**：
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
- 消息截断：根据终端宽度自动截断过长消息
- 非 TTY 降级：管道模式下输出纯文本 `| message`

### 7. Section 进度追踪

```
➤ Clean                           ← PURPLE_BOLD 标题
  | Scanning caches...            ← spinner
  ✓ Removed 42 items (1.5GB)     ← GREEN 成果
  ✓ Nothing to tidy               ← 空区段提示
```

**追踪机制**：
```bash
start_section("Clean")    # 设置 TRACK_SECTION=1, SECTION_ACTIVITY=0
  note_activity()         # 标记有活动
  log_success("...")      # 显示结果
end_section()             # 如果无活动，显示 "Nothing to tidy"
```

### 8. CJK 宽度计算

Mole 用纯 bash 实现 CJK 宽度计算（无外部依赖）：

```bash
get_display_width() {
    char_count = ${#str}   # UTF-8 字符数 (LC_ALL=en_US.UTF-8)
    byte_count = ${#str}   # 字节数 (LC_ALL=C)
    extra_bytes = byte_count - char_count
    width = char_count + extra_bytes / 2
    # "中" (1 char, 3 bytes) → 1 + 1 = 2 ✅
    # "A" (1 char, 1 byte) → 1 + 0 = 1 ✅
}
```

### 9. 日志系统

Mole 的日志分三层：

| 层级 | 输出目标 | 格式 |
|------|---------|------|
| 用户可见 | stdout/stderr | 带颜色+图标 |
| 操作日志 | `~/Library/Logs/mole/operations.log` | 纯文本，带时间戳 |
| 调试日志 | `~/Library/Logs/mole/mole_debug_session.log` | 仅 MO_DEBUG=1 时 |

**日志轮转**：1MB（主日志）/ 5MB（操作日志），自动 `.old` 备份。

---

## Subtap TUI 设计方案

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
