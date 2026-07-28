# Subtap TUI v2 — TUI Studio prototypes

五个可导入的 TUI Studio `.tui` 原型：

| 文件 | 状态 | 唯一视觉焦点 |
| --- | --- | --- |
| `home.tui` | Home | `START NEW TRANSCRIPTION` |
| `new-transcription.tui` | New Transcription | 音频路径输入框与启动按钮 |
| `running.tui` | Running | 进度条与 `STOP RUN` |
| `completed.tui` | Completed | `OPEN SRT` |
| `failed.tui` | Failed | 错误原因与 `RETRY TRANSCRIPTION` |

## 来源与格式

原型按官方仓库当前快照生成：

- Repository: <https://github.com/jalonsogo/tui-studio>
- Commit: `af75d2cc41805e9c6ac9e9de803fefc6c3cc03d0`
- `package.json`: package `tuistudio`, version `0.0.1`
- License: MIT（已核对 `/tmp/tui-studio-official/LICENSE`）
- `.tui` 格式：`{ "version": "1", "meta": {...}, "tree": {...} }`
- 官方导入入口：`Cmd/Ctrl+O`，加载器要求 `version === "1"` 且存在 `tree`

官方仓库没有独立 JSON Schema 文件；本目录没有伪造 schema。验证以官方导入契约、节点字段结构与官方 build 为准。

## 打开与验收

```bash
cd /tmp/tui-studio-official
npm install
npm run dev
```

浏览器打开 `http://localhost:5173`，按 `Cmd+O`，选择本目录中的任一 `.tui` 文件。

Canvas 尺寸依次设为 `60×25`、`90×25`、`104×25` 验收：

1. `<80` 列：左侧 18 列 rail 保持可读，主区填充剩余宽度，不出现横向溢出。
2. `80–103` 列：主区获得更多呼吸空间，但不新增信息栏。
3. `>=104` 列：只增加可伸缩空白，不改变信息层级。
4. 每个状态只有一个主动作焦点；运行中只验收 `STOP RUN`，失败态只验收 `RETRY`。
5. 使用 ANSI 预览和导出时，颜色应保持 dark semantic palette：背景 `#0f1115`、panel `#171b22`、muted `#7d8795`、cyan `#69d2e7`、success `#7dd3a7`、warning `#f2c879`、error `#ef7d88`。

## 约束与已知限制

- `.tui` 只包含字符网格组件树，没有 React/TypeScript 导出代码，也没有产品源码变更。
- 原型文案采用 ASCII，避免把 CJK 宽度误判伪装成已解决。官方当前 `visibleLength` 基于 JavaScript 字符长度；Subtap 的最终 TUI 仍需用 Textual 的终端宽度规则验收 CJK、全角标点和组合字符。
- `NO_COLOR` 运行时应关闭 ANSI 颜色；ASCII 降级时应保留文本层级和 `[O]`、`[X]`、`[R]`、`[Q]` 控制符，边框可降为 `+|-`。这是产品实现验收项，不由 `.tui` 文件强行模拟。
- 这些文件是视觉原型，不宣称 `onClick` 字符串可以直接驱动 Subtap 状态机；事件名仅用于表达动作意图。
