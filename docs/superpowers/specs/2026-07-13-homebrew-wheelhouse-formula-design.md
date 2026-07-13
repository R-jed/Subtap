# Homebrew 锁定 Wheelhouse Formula 设计

## 背景与结论

`v0.1.0rc2` 已通过 GitHub prerelease、SHA256、构建来源证明和 arm64 wheel smoke。标准 Python Formula 原型在 `brew update-python-resources` 阶段失败，因为 `mlx` 只提供二进制 wheel，没有可用源码包。

本设计验证 **Formula + 锁定 Apple Silicon wheelhouse**。它是一个有明确终止条件的分发实验，不代表 Formula 已被接受：只有真实 `brew audit --strict`、冷安装、升级、回滚和卸载全部通过后，ADR 才能从 `Proposed` 改为 `Accepted`。

## 用户契约

- 用户命令最终保持 `brew install r-jed/tap/subtap`。
- 用户不需要安装、选择或理解 Python；Formula 依赖固定的 Homebrew Python。
- 模型不进入 Homebrew 包，首次启动后由 Subtap 模型管理器下载。
- `brew uninstall subtap` 只删除程序，不删除 `~/.subtap`。
- 仅支持 Apple Silicon macOS；其他架构在安装前明确失败。

## 发布产物

RC workflow 在真实 arm64 macOS runner 上生成：

```text
subtap-0.1.0rcN-macos-arm64-wheelhouse.tar.gz
├── requirements.txt
└── wheels/
    ├── subtap-0.1.0rcN-py3-none-any.whl
    └── 所有运行依赖的当前 macOS arm64 wheel
```

规则：

- runner 首先断言 `uname -m` 为 `arm64`，禁止依赖 runner 标签推断架构。
- 使用锁文件解析当前项目的运行依赖，不包含 dev/ai 可选依赖和模型。
- 只允许 wheel；任一依赖需要现场源码构建即失败。
- `requirements.txt` 对每个本地 wheel 使用 SHA256，安装时强制 `--no-index --require-hashes`。
- 归档和 `SHA256SUMS` 上传同一 GitHub prerelease，并生成来源证明。
- 生成依赖名称、版本、许可证清单。出现项目规则禁止的 GPL 类依赖时停止，不发布 wheelhouse。

## Formula

Tap 只保留一个 `Formula/subtap.rb`：

- `url` 指向正式 GitHub Release 的 arm64 wheelhouse，不引用临时 CI artifact。
- `sha256` 固定整个 wheelhouse。
- `depends_on arch: :arm64`。
- 固定兼容的 `python@3.12`，并依赖 Homebrew `ffmpeg`。
- 在 `libexec` 创建隔离虚拟环境。
- 只从归档内 wheels 安装，禁止访问 PyPI、GitHub 或镜像。
- 将 `libexec/bin/subtap` 链接到 Formula 的 `bin`。

Formula test 使用临时 HOME：

1. `subtap version` 必须等于 Formula 版本。
2. `subtap doctor --json` 必须输出合法 JSON。
3. 未安装模型时，只允许明确的模型缺失状态；`models_error` 或其他检查错误必须失败。
4. 不下载模型、不访问真实用户目录。

## 验收顺序

候选 Formula 只在一次性 GitHub macOS runner 和明确授权的本地验收环境执行：

1. `brew audit --strict r-jed/tap/subtap`。
2. 冷安装 Formula。
3. 执行 version、Doctor 和 TUI help smoke。
4. 使用上一候选 Formula 安装旧版，再升级到当前候选并确认版本变化。
5. 回退上一候选并确认版本恢复。
6. 卸载并确认 models、glossaries、manuscripts、jobs 哨兵文件全部保留。

所有步骤都是硬门禁。缺少上一候选、审计警告、安装失败或无法证明资料保留时，不得显示“验收通过”。

## 失败与终止条件

出现以下任一情况，立即停止 Formula 路线并把证据写入 ADR：

- `brew audit --strict` 拒绝二进制 wheel 或 wheelhouse 布局。
- 任一依赖没有兼容的 macOS arm64 wheel。
- Python/MLX 原生库在隔离环境中无法加载。
- wheelhouse 包含许可证不兼容依赖。
- Formula 必须联网补装、修改动态库路径或依赖用户 Python 才能运行。
- 安装、升级、回滚或卸载无法重复通过。

终止后进入 Cask 自包含运行时设计，不在 Formula 中增加下载器、运行时补丁或降级逻辑。

## 测试与可观测性

- wheelhouse 生成器使用小型单元测试验证平台过滤、SHA256 和许可证拒绝行为。
- Formula 内容测试验证固定 URL、哈希、架构、离线安装参数和用户目录边界。
- workflow 保存 wheelhouse 清单、审计日志、安装日志和验收 JSON。
- ADR 记录每次候选的 Release URL、runner 架构、安装体积、命令结果和失败原因。
- README 只有 ADR Accepted 且真实 Tap 验收通过后才展示安装命令。

## 非目标

- 不发布 Intel、Linux 或 Windows 包。
- 不把模型放进 wheelhouse。
- 不在本阶段发布 PyPI 正式版。
- 不自动创建正式 tag。
- 不保留标准源码 Formula、Cask 和 launcher 三套并行实现。
