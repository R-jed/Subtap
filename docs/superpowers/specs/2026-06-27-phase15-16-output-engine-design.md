# Phase 15 + 16：Output Engine 设计规格

## 概述

将 Subtap 从"散落文件写入"升级为"统一 Output Engine 控制"，实现输出系统统一、性能分析、TUI UX 优化、发布收口。

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                      CLI Layer                          │
│  subtap run input.mp3 --timestamp -o ./output          │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                   OutputEngine                          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐  │
│  │   Naming    │ │  Versioning │ │   Lifecycle     │  │
│  │  Strategy   │ │   System    │ │   Controller    │  │
│  └─────────────┘ └─────────────┘ └─────────────────┘  │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    TUI Layer                            │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Progress Bars + Color Scheme + Status Display  │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## 文件结构

```
src/subtap/
  ├── output/
  │   ├── __init__.py
  │   ├── engine.py          # OutputEngine 核心
  │   ├── lifecycle.py       # 输出生命周期控制
  │   ├── naming.py          # 命名策略系统
  │   ├── versioning.py      # 版本管理系统
  │   └── exceptions.py      # 输出异常定义
  ├── schemas/
  │   └── config.py          # 修改：添加 OutputConfig
  ├── ui/
  │   ├── tui.py             # 修改：绑定输出状态
  │   ├── progress.py        # 修改：添加输出进度
  │   └── colors.py          # 新增：颜色方案
  └── cli.py                 # 修改：集成 OutputEngine
```

## 核心组件

### OutputEngine

```python
class OutputEngine:
    def __init__(self, output_dir: Path, input_name: str, config: OutputConfig):
        self.output_dir = output_dir
        self.input_name = input_name
        self.config = config
        self.version = self._next_version()
        self.naming = NamingStrategy(input_name, config.timestamp)
        self.lifecycle = OutputLifecycle(self._get_version_dir())
        
    def _get_version_dir(self) -> Path:
        return self.output_dir / self.input_name / f"v{self.version}"
        
    def _next_version(self) -> int:
        # 原子操作，支持并发
        ...
        
    def _create_latest_link(self) -> None:
        """创建 latest 符号链接"""
        ...
        
    def cleanup_old_versions(self) -> None:
        """清理旧版本，保留最近 N 个"""
        ...
        
    def finalize_output(self) -> dict:
        """完成输出，创建符号链接，清理旧版本"""
        self._create_latest_link()
        self.cleanup_old_versions()
        return self.lifecycle.finalize_output()
```

### OutputLifecycle

```python
class OutputLifecycle:
    def __init__(self, version_dir: Path):
        self.version_dir = version_dir
        self.version_dir.mkdir(parents=True, exist_ok=True)
        self._artifacts_dir = self.version_dir / "artifacts"
        self._artifacts_dir.mkdir(exist_ok=True)
        
    def init_output_task(self) -> None:
        """初始化输出任务"""
        
    def write_user_artifact(self, name: str, content: str) -> Path:
        """写入用户可见文件"""
        try:
            output_path = self.version_dir / name
            output_path.write_text(content, encoding="utf-8")
            return output_path
        except OSError as e:
            logger.error("写入文件失败: %s - %s", name, e)
            raise OutputError(f"写入 {name} 失败: {e}") from e
        
    def write_report(self, content: str) -> Path:
        """写入报告"""
        
    def write_metrics(self, metrics: dict) -> Path:
        """写入性能指标"""
        
    def write_artifacts(self, artifacts: dict) -> Path:
        """写入中间文件"""
        
    def finalize_output(self) -> dict:
        """生成校验和，返回输出清单"""
```

### NamingStrategy

```python
class NamingStrategy:
    def __init__(self, input_name: str, use_timestamp: bool = True):
        self.input_name = Path(input_name).stem
        self.use_timestamp = use_timestamp
        
    def get_final_name(self, ext: str) -> str:
        """获取最终文件名"""
        return f"{self.input_name}.{ext}"
        
    def get_report_name(self) -> str:
        return f"{self.input_name}_report.md"
        
    def get_metrics_name(self) -> str:
        return f"{self.input_name}_metrics.json"
        
    def get_artifact_name(self, name: str) -> str:
        return f"{self.input_name}_{name}.json"
```

## 输出目录结构

```
output/
  └── video/
      ├── v1/
      │   ├── video.srt
      │   ├── video_report.md
      │   ├── video_metrics.json
      │   ├── video_run.log.jsonl
      │   └── artifacts/
      │         ├── video_asr.json
      │         ├── video_segments.json
      │         ├── video_align.json
      │         └── video_quality.json
      └── latest -> v1
```

## 配置集成

```python
# schemas/config.py
class OutputConfig(BaseModel):
    """输出配置"""
    timestamp: bool = True  # 默认开启时间戳
    keep_versions: int = 5  # 保留版本数
    generate_artifacts: bool = True  # 是否生成中间文件

class SubtapConfig(BaseModel):
    # ... 其他配置
    output: OutputConfig = Field(default_factory=OutputConfig)
```

## CLI 集成

```python
@app.command()
def run(
    input_path: Path,
    output_dir: Path = Path("./output"),
    timestamp: bool = typer.Option(True, "--timestamp/--no-timestamp", help="输出目录是否带时间戳"),
    # ... 其他参数
) -> None:
    # 加载配置
    config = load_config()
    config.output.timestamp = timestamp  # CLI 参数覆盖配置
    
    # 创建 OutputEngine
    engine = OutputEngine(output_dir, input_path.stem, config.output)
    
    # 执行 pipeline
    runner = TUIRunner(use_tui=True, output_engine=engine)
    result = runner.run_pipeline(pipeline, input_path, output_dir)
    
    # 完成输出
    engine.finalize_output()
```

## TUI 显示方案

### 颜色定义

```python
from rich.style import Style

STAGE_TITLE = Style(color="blue", bold=True)      # 阶段标题
PROGRESS_BAR = Style(color="green")               # 进度条完成
PROGRESS_ACTIVE = Style(color="yellow")           # 进行中
ERROR = Style(color="red", bold=True)             # 错误
FILE_PATH = Style(color="cyan")                   # 文件路径
TIMING = Style(color="dim")                       # 耗时统计
SUCCESS = Style(color="green", bold=True)         # 成功标记
HEADER = Style(color="white", bold=True)          # 汇总标题
```

### 显示效果

```
═══ Subtap 字幕生成 ═══

[1/7] ▸ 音频标准化
  ████████████████████████████████████████ 100% (1.2s)
  ✓ 输出：work/audio/source.wav

[2/7] ▸ 语音识别
  ████████████████████████████████████████ 100% (15.3s)
  ✓ 输出：work/asr/asr.jsonl (156 条)

═══ 输出文件生成 ═══

▸ video.srt
  ████████████████████████████████████████ 100% (89/89 行)
  ✓ 156 行，3.2 KB

▸ video_report.md
  ████████████████████████████████████████ 100% (5/5 段)
  ✓ 2.3 KB

═══ 完成 ═══

📁 输出目录：output/video/v1/
⏱️ 总耗时：24.8s
📊 质量评分：92/100
```

## 错误处理

```python
class OutputError(Exception):
    """输出错误"""
    pass

class OutputLifecycle:
    def write_user_artifact(self, name: str, content: str) -> Path:
        try:
            output_path = self.version_dir / name
            output_path.write_text(content, encoding="utf-8")
            return output_path
        except OSError as e:
            logger.error("写入文件失败: %s - %s", name, e)
            raise OutputError(f"写入 {name} 失败: {e}") from e
```

## 并发安全

```python
class OutputEngine:
    def _next_version(self) -> int:
        """获取下一个版本号（原子操作）"""
        import fcntl
        
        lock_file = self.output_dir / self.input_name / ".version_lock"
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(lock_file, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                existing = list(self.output_dir.glob(f"{self.input_name}/v*"))
                if not existing:
                    return 1
                versions = [int(p.name[1:]) for p in existing]
                return max(versions) + 1
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
```

## 旧版本清理

```python
class OutputEngine:
    def cleanup_old_versions(self) -> None:
        """清理旧版本，保留最近 N 个"""
        existing = sorted(
            self.output_dir.glob(f"{self.input_name}/v*"),
            key=lambda p: int(p.name[1:])
        )
        
        if len(existing) <= self.config.keep_versions:
            return
            
        for old_version in existing[:-self.config.keep_versions]:
            shutil.rmtree(old_version)
            logger.info("清理旧版本: %s", old_version)
```

## 日志格式

### 执行日志

```json
{
    "timestamp": "2026-06-27T10:30:00Z",
    "stage": "asr",
    "status": "completed",
    "duration_sec": 15.3,
    "details": {
        "segment_count": 156,
        "model": "qwen3-asr-0.6b"
    }
}
```

### 性能日志

```json
{
    "timestamp": "2026-06-27T10:30:00Z",
    "metrics": {
        "total_duration_sec": 24.8,
        "stages": {
            "prepare": 1.2,
            "chunk": 0.3,
            "asr": 15.3,
            "clean": 2.1,
            "segment": 0.8,
            "align": 5.2,
            "export": 0.1
        }
    }
}
```

## 验收标准

1. ✔ 所有输出文件由 OutputEngine 生成
2. ✔ pipeline 无直接 file write
3. ✔ output 结构一致（每个版本目录结构相同）
4. ✔ run 可重复执行（相同输入生成相同版本号）
5. ✔ TUI 状态完整展示（每个阶段有进度条）
6. ✔ 无散点输出（所有文件在统一目录）
7. ✔ latest 符号链接正确指向最新版本
8. ✔ 旧版本自动清理（保留最近 5 个）
9. ✔ 错误处理完善（写入失败有明确错误信息）
10. ✔ 并发安全（多个实例不会版本冲突）
11. ✔ 所有测试通过
12. ✔ TUI 颜色方案符合设计
