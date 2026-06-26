# Graph Report - Subtap  (2026-06-27)

## Corpus Check
- 97 files · ~37,494 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1665 nodes · 2757 edges · 98 communities (81 shown, 17 thin omitted)
- Extraction: 74% EXTRACTED · 24% INFERRED · 0% AMBIGUOUS · INFERRED: 659 edges (avg confidence: 0.62)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `31a093dd`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_导出模块|导出模块]]
- [[_COMMUNITY_分段处理|分段处理]]
- [[_COMMUNITY_断句引擎|断句引擎]]
- [[_COMMUNITY_报告生成|报告生成]]
- [[_COMMUNITY_文档说明|文档说明]]
- [[_COMMUNITY_任务系统|任务系统]]
- [[_COMMUNITY_ASR后处理|ASR后处理]]
- [[_COMMUNITY_术语学习|术语学习]]
- [[_COMMUNITY_Git防护|Git防护]]
- [[_COMMUNITY_对齐引擎|对齐引擎]]
- [[_COMMUNITY_清洁室检查|清洁室检查]]
- [[_COMMUNITY_HTTP ASR后端|HTTP ASR后端]]
- [[_COMMUNITY_模型测试|模型测试]]
- [[_COMMUNITY_媒体处理|媒体处理]]
- [[_COMMUNITY_进度UI|进度UI]]
- [[_COMMUNITY_管道控制|管道控制]]
- [[_COMMUNITY_执行策略|执行策略]]
- [[_COMMUNITY_质量评分|质量评分]]
- [[_COMMUNITY_CLI测试|CLI测试]]
- [[_COMMUNITY_质量修复|质量修复]]
- [[_COMMUNITY_配置管理|配置管理]]
- [[_COMMUNITY_状态管理|状态管理]]
- [[_COMMUNITY_事件系统|事件系统]]
- [[_COMMUNITY_ASR测试|ASR测试]]
- [[_COMMUNITY_清理测试|清理测试]]
- [[_COMMUNITY_分段测试|分段测试]]
- [[_COMMUNITY_对齐测试|对齐测试]]
- [[_COMMUNITY_LLM后端|LLM后端]]
- [[_COMMUNITY_MLX ASR|MLX ASR]]
- [[_COMMUNITY_Ollama后端|Ollama后端]]
- [[_COMMUNITY_OpenAI兼容|OpenAI兼容]]
- [[_COMMUNITY_替换规则|替换规则]]
- [[_COMMUNITY_VAD检测|VAD检测]]
- [[_COMMUNITY_数据模型|数据模型]]
- [[_COMMUNITY_工作空间|工作空间]]
- [[_COMMUNITY_流水线核心|流水线核心]]
- [[_COMMUNITY_后端注册|后端注册]]
- [[_COMMUNITY_日志系统|日志系统]]
- [[_COMMUNITY_FFmpeg工具|FFmpeg工具]]
- [[_COMMUNITY_测试配置|测试配置]]
- [[_COMMUNITY_错误检测|错误检测]]
- [[_COMMUNITY_决策引擎|决策引擎]]
- [[_COMMUNITY_MLX对齐|MLX对齐]]
- [[_COMMUNITY_Mock后端|Mock后端]]
- [[_COMMUNITY_导出测试|导出测试]]
- [[_COMMUNITY_CLI入口|CLI入口]]
- [[_COMMUNITY_管道测试|管道测试]]
- [[_COMMUNITY_任务测试|任务测试]]
- [[_COMMUNITY_质量测试|质量测试]]
- [[_COMMUNITY_工程卫生|工程卫生]]
- [[_COMMUNITY_术语测试|术语测试]]
- [[_COMMUNITY_媒体测试|媒体测试]]
- [[_COMMUNITY_断句测试|断句测试]]
- [[_COMMUNITY_对齐后处理|对齐后处理]]
- [[_COMMUNITY_LLM基础|LLM基础]]
- [[_COMMUNITY_ASR基础|ASR基础]]
- [[_COMMUNITY_对齐基础|对齐基础]]
- [[_COMMUNITY_进度条|进度条]]
- [[_COMMUNITY_TUI界面|TUI界面]]
- [[_COMMUNITY_事件总线|事件总线]]
- [[_COMMUNITY_策略配置|策略配置]]
- [[_COMMUNITY_状态持久化|状态持久化]]
- [[_COMMUNITY_清洁工作区|清洁工作区]]
- [[_COMMUNITY_Git状态|Git状态]]
- [[_COMMUNITY_模型路径|模型路径]]
- [[_COMMUNITY_Pydantic模型|Pydantic模型]]
- [[_COMMUNITY_YAML配置|YAML配置]]
- [[_COMMUNITY_测试夹具|测试夹具]]
- [[_COMMUNITY_GlossaryLearner|GlossaryLearner]]
- [[_COMMUNITY_CleanEngine|CleanEngine]]
- [[_COMMUNITY_SentenceEngine|SentenceEngine]]
- [[_COMMUNITY_AlignEngine|AlignEngine]]
- [[_COMMUNITY_PipelineDecision|PipelineDecision]]
- [[_COMMUNITY_PipelineController|PipelineController]]
- [[_COMMUNITY_QualityScorer|QualityScorer]]
- [[_COMMUNITY_Workspace|Workspace]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 84|Community 84]]
- [[_COMMUNITY_Community 85|Community 85]]
- [[_COMMUNITY_Community 86|Community 86]]
- [[_COMMUNITY_Community 87|Community 87]]
- [[_COMMUNITY_Community 88|Community 88]]
- [[_COMMUNITY_Community 89|Community 89]]
- [[_COMMUNITY_Community 90|Community 90]]
- [[_COMMUNITY_Community 91|Community 91]]
- [[_COMMUNITY_Community 92|Community 92]]
- [[_COMMUNITY_Community 93|Community 93]]
- [[_COMMUNITY_Community 94|Community 94]]
- [[_COMMUNITY_Community 95|Community 95]]
- [[_COMMUNITY_Community 96|Community 96]]
- [[_COMMUNITY_Community 97|Community 97]]

## God Nodes (most connected - your core abstractions)
1. `SubtapConfig` - 69 edges
2. `Workspace` - 66 edges
3. `PipelineController` - 37 edges
4. `Glossary` - 30 edges
5. `ErrorDetector` - 29 edges
6. `_config_with_model_root()` - 29 edges
7. `Task` - 28 edges
8. `PipelineState` - 27 edges
9. `Pipeline` - 25 edges
10. `SetupWizard` - 25 edges

## Surprising Connections (you probably didn't know these)
- `test_get_aligner_mock()` --calls--> `get_aligner_backend()`  [INFERRED]
  tests/test_align.py → src/subtap/backends/align/__init__.py
- `Path` --uses--> `AlignerBackend`  [INFERRED]
  tests/test_align.py → src/subtap/backends/align/base.py
- `SubtapConfig` --uses--> `AlignerBackend`  [INFERRED]
  tests/test_align.py → src/subtap/backends/align/base.py
- `Workspace` --uses--> `AlignerBackend`  [INFERRED]
  tests/test_align.py → src/subtap/backends/align/base.py
- `Path` --uses--> `MockAligner`  [INFERRED]
  tests/test_align.py → src/subtap/backends/align/mock.py

## Import Cycles
- None detected.

## Communities (98 total, 17 thin omitted)

### Community 0 - "导出模块"
Cohesion: 0.05
Nodes (61): ABC, ASSExporter, BaseExporter, _fmt_ass_time(), _fmt_srt_time(), load_aligned(), Subtitle export: aligned.jsonl → SRT / ASS / TXT., Plain text exporter with timestamps. (+53 more)

### Community 1 - "分段处理"
Cohesion: 0.05
Nodes (54): load_clean_segments(), Segment pipeline stage: cleaned.jsonl → sentences.jsonl., Load CleanSegments from JSONL., Write SentenceSegments to JSONL., Run segment stage: load cleaned → split → sentences.jsonl.      Args:         wo, run_segment(), write_sentences(), _allocate_time() (+46 more)

### Community 2 - "断句引擎"
Cohesion: 0.06
Nodes (24): SentenceEngine: unified sentence segmentation with spaCy PRIMARY + rule-based FA, Split using spaCy sentencizer (PRIMARY).          Args:             texts: Text, Split on punctuation boundaries (FALLBACK).          Args:             texts: Te, Split long sentences to meet character limit.          Args:             segment, Adjust timing to meet CPS constraint (POST).          Args:             segments, Split long text at natural boundaries.          Args:             text: Text to, Unified sentence segmentation engine.      Single decision path: spaCy PRIMARY →, Initialize sentence engine.          Args:             use_spacy: Whether to use (+16 more)

### Community 3 - "报告生成"
Cohesion: 0.06
Nodes (49): Pipeline, Pipeline orchestrator with stage-based execution., Execute Subtap stages with workspace-backed state.      Each stage reads from an, Run a single pipeline stage., generate_report(), Report generator for subtitle quality analysis., Generate a Markdown report for subtitle quality analysis.      Args:         qua, load_config() (+41 more)

### Community 4 - "文档说明"
Cohesion: 0.20
Nodes (14): Apple MLX, Pipeline, Qwen3-ASR, Qwen3-ForcedAligner, config.py, glossary.py, mlx-audio, ollama (+6 more)

### Community 5 - "任务系统"
Cohesion: 0.08
Nodes (25): Path, Task abstraction for one-command subtitle generation., Result of a completed subtitle generation task., One-command subtitle generation task.      Encapsulates a complete subtitle gene, Whether to skip LLM cleaning based on mode., Whether to skip alignment based on mode., ASR model size based on mode., Create output directory structure and return paths.          Args:             o (+17 more)

### Community 6 - "ASR后处理"
Cohesion: 0.07
Nodes (24): CleanEngine, CleanEngine: unified ASR post-processing with deterministic PRIMARY + optional E, Restore punctuation using spaCy ENHANCER with rule-based fallback.          Prio, Normalize entities using rapidfuzz ENHANCER with exact match fallback., Unified ASR post-processing engine.      Single decision path: deterministic PRI, Initialize clean engine.          Args:             use_spacy: Whether to use sp, Initialize spaCy for punctuation restore., Initialize rapidfuzz for fuzzy matching. (+16 more)

### Community 7 - "术语学习"
Cohesion: 0.07
Nodes (29): GlossaryLearner, GlossaryUpdate, Glossary learner: detect repeated errors, extract domain terms, learn correction, Extract potential domain-specific terms.          Simple heuristic: terms with h, Learn patterns from user corrections.          Args:             corrections: Us, Glossary update suggestions from learning., Learn glossary updates from ASR errors and user corrections.      Uses rapidfuzz, Initialize rapidfuzz with fallback. (+21 more)

### Community 8 - "Git防护"
Cohesion: 0.08
Nodes (25): GitGuard, Git state guard — validates and auto-commits before pipeline execution., Auto-commit dirty state with checkpoint message.          Only commits if there, Git state validation and auto-commit for pipeline safety.      Ensures the works, Check if workspace is inside a git repository., Get structured git state info.          Returns:             {                 ", Validate git state before pipeline execution.          Returns:             {"ok, GitGuard (+17 more)

### Community 9 - "对齐引擎"
Cohesion: 0.08
Nodes (23): AlignEngine, AlignEngine: unified alignment post-processing.  Architecture: - PRIMARY: forced, Snap timing boundaries to silence points.          Args:             segments: A, Unified alignment post-processing engine.      Single decision path: alignment P, Initialize align engine.          Args:             tolerance_ms: Maximum smooth, Full alignment refinement pipeline.          Flow: smoothing → overlap fix → sil, Smooth timing jumps within tolerance.          Args:             segments: Align, Fix overlapping time ranges.          Args:             segments: Aligned segmen (+15 more)

### Community 10 - "清洁室检查"
Cohesion: 0.09
Nodes (19): Cleanroom, Workspace hygiene checks before pipeline execution., Report model availability.          Returns:             {"models": [{"name": st, Workspace hygiene checker and cleaner.      Rules:     - Never delete user outpu, Check workspace state without modifying anything.          Returns:, Remove temp files and fix corrupt logs.          Never removes user output (SRT,, Any, Path (+11 more)

### Community 11 - "HTTP ASR后端"
Cohesion: 0.08
Nodes (28): HttpASRBackend, HTTP ASR backend stub.  OpenAI-compatible POST /v1/audio/transcriptions interfac, Stub HTTP ASR backend for future OpenAI-compatible API integration., Transcribe chunks via HTTP API (stub).          Future implementation will POST, get_backend(), ASR backend registry and factory., Instantiate an ASR backend by name., MLXQwenASR (+20 more)

### Community 12 - "模型测试"
Cohesion: 0.13
Nodes (21): _config_with_model_root(), Tests for model management system., CLI models status runs without crash., Config with model root pointing to tmp., CLI models verify runs without crash., CLI models install shows expected file location., Test CLI models list command., Test CLI models remove command. (+13 more)

### Community 13 - "媒体处理"
Cohesion: 0.14
Nodes (15): VAD-based silence splitting using pydub., Split source audio into chunks based on silence detection.      Uses pydub's det, split_chunks(), Chunk, SubtapConfig, Workspace, Path, SubtapConfig (+7 more)

### Community 14 - "进度UI"
Cohesion: 0.05
Nodes (30): Exception, PipelineState, Exception, Exception, Path, Table, _build_stage_table(), PipelineProgress (+22 more)

### Community 15 - "管道控制"
Cohesion: 0.09
Nodes (17): PipelineController, PipelineController: state-machine driven pipeline execution with retry, skip, re, Retry a failed stage., Rollback a stage to PENDING state., Resume pipeline from the first non-success stage., Execute a stage with automatic retry on failure., State-machine driven pipeline execution.      Supports: run, retry, skip, resume, Set pre-flight state for event logging. (+9 more)

### Community 16 - "执行策略"
Cohesion: 0.09
Nodes (13): ExecutionPolicy, PolicyMode, Execution policy: controls model selection, LLM usage, and alignment precision., Determines how the pipeline executes based on user preference., Execution policy modes., LOCAL_ONLY policy: no LLM, align enabled., HYBRID policy: LLM enabled, 1.7B model., FAST_MODE policy: skips clean and align. (+5 more)

### Community 17 - "质量评分"
Cohesion: 0.12
Nodes (13): QualityReport, Quality scoring system for aligned subtitle segments., Score segmentation quality (0-100)., Score readability (0-100)., Quality assessment report for subtitle data., Scores subtitle quality based on aligned segments., Calculate quality score for the aligned file.          Returns:             Qual, Load aligned segments from JSONL. (+5 more)

### Community 18 - "CLI测试"
Cohesion: 0.06
Nodes (37): Tests for CLI commands., subtap run should accept --mode fast., subtap run should accept --mode quality., subtap run should accept --mode hybrid., subtap analyze command should exist., subtap version should print version string., Test that setup command exists., Test setup system check step. (+29 more)

### Community 19 - "质量修复"
Cohesion: 0.14
Nodes (13): ErrorReport, FixAction, Fixer, Auto-fix system for subtitle errors., Fix overlapping time ranges by adjusting end_sec., Record of a fix action taken., Auto-fix subtitle errors based on error reports., Apply fixes for detected errors.          Args:             errors: List of Erro (+5 more)

### Community 20 - "配置管理"
Cohesion: 0.16
Nodes (22): GlossaryTerm, A canonical term with optional aliases., _make_asr_jsonl(), Path, SubtapConfig, Workspace, Tests for clean pipeline stage: glossary + replacement + LLM., Write mock ASR segments to asr.jsonl. (+14 more)

### Community 21 - "状态管理"
Cohesion: 0.06
Nodes (36): Path, Tests for engine: state machine, policy, controller, events., State changes trigger listener callbacks., Reset returns stage to PENDING., Events are written to JSONL and can be read back., get_events can filter by stage name., All expected statuses exist., Controller transitions stages through states correctly. (+28 more)

### Community 22 - "事件系统"
Cohesion: 0.09
Nodes (32): BaseModel, AudioConfig, ModelConfig, OutputConfig, Pydantic v2 config schema with default merge., VAD / silence splitting parameters., Audio extraction and processing settings., Model management configuration. (+24 more)

### Community 23 - "ASR测试"
Cohesion: 0.48
Nodes (3): _get_model_root(), Resolve model root path from config., SubtapConfig

### Community 24 - "清理测试"
Cohesion: 0.13
Nodes (16): CleanConfig, get_llm_backend(), LLM backend registry and factory., Instantiate an LLM backend by name.      Supports formats:       - "ollama:<mode, LMStudioLLM, LMStudio LLM backend stub.  LMStudio exposes an OpenAI-compatible API locally. T, LLM backend using LMStudio local API (stub)., LMStudio stub — delegates to OpenAI-compatible API.          LMStudio serves at (+8 more)

### Community 25 - "分段测试"
Cohesion: 0.13
Nodes (10): EventLogger, Event logging system for pipeline execution observability., Event-based logger that writes structured JSONL for pipeline observability., Log a pipeline event., Read events, optionally filtered by stage., Path, Retry events are logged with retry count., clear() removes all events. (+2 more)

### Community 26 - "对齐测试"
Cohesion: 0.11
Nodes (12): PipelineState, Stage state machine for pipeline execution., State of a single pipeline stage with retry tracking., Transition to a new status., Tracks the state of all stages in a pipeline run., StageState, New StageState is PENDING., can_retry is True only when FAILED and retries remain. (+4 more)

### Community 27 - "LLM后端"
Cohesion: 0.20
Nodes (18): _make_sentences_jsonl(), Path, SubtapConfig, Workspace, Tests for forced alignment stage., Aligned segments have monotonic time., AlignedSegment text matches source SentenceSegment text., CLI align command runs without crash. (+10 more)

### Community 28 - "MLX ASR"
Cohesion: 0.14
Nodes (15): get_aligner_backend(), Aligner backend registry and factory., Instantiate an aligner backend by name., MLXQwenAligner, MLX Qwen ForcedAligner implementation.  Uses mlx_audio.stt.generate_transcriptio, Forced alignment backend using mlx_audio STT with text prompt., MockAligner, Mock aligner for testing. (+7 more)

### Community 29 - "Ollama后端"
Cohesion: 0.12
Nodes (11): PipelineDecision, PipelineMode, Decision engine: centralized pipeline routing and strategy selection.  This is t, Pipeline execution modes., Centralized decision for pipeline execution., Create decision from mode string.          Args:             mode: One of "fast", Whether to run clean stage., Whether to run align stage. (+3 more)

### Community 30 - "OpenAI兼容"
Cohesion: 0.13
Nodes (13): apply_replacements(), Deterministic text replacement (before LLM stage).  Only performs string replace, Apply deterministic replacements to ASR segments.      Runs glossary replacement, Glossary, Loaded glossary with normalized lookup structures., Build case-insensitive alias → canonical map., Resolve a term to its canonical form (case-insensitive)., Return (find, replace) pairs for deterministic replacement. (+5 more)

### Community 31 - "替换规则"
Cohesion: 0.18
Nodes (6): Workspace directory management., Manages the work/ directory structure for a pipeline run., Create all workspace subdirectories., Workspace, Path, SubtapConfig

### Community 32 - "VAD检测"
Cohesion: 0.06
Nodes (39): Setup wizard business logic., User-level setup wizard for Subtap., Check system dependencies.          Returns:             Dict mapping dependency, Check if ~/.subtap/config.yaml exists., Run init command internally.          Returns:             True if init succeede, Setup models based on mode.          Args:             mode: Execution mode (fas, Download a single model.          Args:             downloader: ModelDownloader, SetupWizard (+31 more)

### Community 33 - "数据模型"
Cohesion: 0.16
Nodes (9): ErrorReport, Error detection for aligned subtitle segments., Check for segments without punctuation (bad segmentation)., Check for large time gaps between segments., A detected error in subtitle data., Detect all errors in the aligned file.          Returns:             List of Err, Load aligned segments from JSONL., Check for segments that are too long (>42 chars or >2 lines). (+1 more)

### Community 34 - "工作空间"
Cohesion: 0.17
Nodes (12): load_chunks(), ASR pipeline stage: load chunks → transcribe → write asr.jsonl., Load chunks from JSONL file., Write ASR segments to JSONL., Run ASR stage: load chunks, transcribe, write asr.jsonl.      Args:         work, run_asr(), write_asr_segments(), ASRSegment (+4 more)

### Community 35 - "流水线核心"
Cohesion: 0.06
Nodes (31): Tests for output system., Test writing artifacts., Test finalizing output., Test NamingStrategy generates correct final name., Test old version cleanup., Test OutputEngine initialization., Test writing final output., Test writing metrics. (+23 more)

### Community 36 - "后端注册"
Cohesion: 0.07
Nodes (27): CLI 命令结构, Phase 14: Subtap 安装与用户交付系统设计, ~/.subtap/config.yaml 结构, `subtap doctor` 增强, `subtap init` 设计（开发级）, `subtap models` 增强, `subtap setup` 设计, 下载规则 (+19 more)

### Community 37 - "日志系统"
Cohesion: 0.19
Nodes (13): Path, SubtapConfig, Tests for ASR pipeline stage., CLI transcribe command runs without crash (mock backend)., MockASRBackend satisfies the ASRBackend protocol., get_backend raises ValueError for unknown backend name., Full pipeline: prepare → chunk → mock ASR → asr.jsonl., ASR segment chunk_ids must align with chunk chunk_ids. (+5 more)

### Community 38 - "FFmpeg工具"
Cohesion: 0.09
Nodes (18): Initialize output engine.          Args:             output_dir: Base output dir, Version management for output system., Manages output versions., Initialize version manager.          Args:             output_dir: Base output d, Get next version number.          Returns:             Next version number, Get version directory path.          Args:             version: Version number, Create latest symlink.          Args:             version: Version to point to, Clean up old versions.          Args:             keep_last: Number of recent ve (+10 more)

### Community 39 - "测试配置"
Cohesion: 0.15
Nodes (13): load_asr_segments(), Clean pipeline stage: ASR segments → replacement → LLM → cleaned.jsonl., Load ASR segments from JSONL., Write clean segments to JSONL., Run clean stage: load ASR → replacement → LLM → cleaned.jsonl.      Steps:     1, run_clean(), write_clean_segments(), ASRSegment (+5 more)

### Community 40 - "错误检测"
Cohesion: 0.22
Nodes (8): OllamaLLM, Ollama LLM backend for text cleaning., LLM backend using Ollama local API., Build a single prompt for batch cleaning., Parse LLM response and map back to segments., Send segments to Ollama for cleaning., CleanSegment, Glossary

### Community 41 - "决策引擎"
Cohesion: 0.31
Nodes (6): ErrorDetector, Detects errors in aligned subtitle segments., Path, Path, Test error detection system., TestErrorDetector

### Community 42 - "MLX对齐"
Cohesion: 0.09
Nodes (21): CLI 集成, NamingStrategy, OutputEngine, OutputLifecycle, Phase 15 + 16：Output Engine 设计规格, TUI 显示方案, 并发安全, 性能日志 (+13 more)

### Community 43 - "Mock后端"
Cohesion: 0.22
Nodes (7): Lazy-load the MLX alignment model., Load chunk metadata for offset and path lookup., Resolve chunk WAV file absolute path., Align sentences to audio using forced alignment.          Each sentence is align, AlignedSegment, Path, SentenceSegment

### Community 44 - "导出测试"
Cohesion: 0.22
Nodes (8): Pass-through: return original timing., AlignConfig, Forced alignment backend configuration., AlignConfig, AlignConfig, AlignedSegment, Path, SentenceSegment

### Community 45 - "CLI入口"
Cohesion: 0.27
Nodes (9): MediaInfo, Path, extract_audio(), _find_binary(), probe_media(), FFmpeg / FFprobe wrapper utilities., Find ffmpeg/ffprobe binary, raise if not found., Run ffprobe and parse into MediaInfo. (+1 more)

### Community 46 - "管道测试"
Cohesion: 0.22
Nodes (9): Logger, Path, get_user_logger(), Logging system with Chinese translation layer for user-facing messages., Translate English log messages to Chinese for user display.      Only translates, Set up file-only logger (English, for debugging)., Get logger for user-facing messages (Chinese)., setup_file_logger() (+1 more)

### Community 47 - "任务测试"
Cohesion: 0.22
Nodes (7): AlignerBackend, Aligner backend Protocol definition., Protocol for forced alignment backends.      Receives sentence segments + audio, Align sentences to audio waveform for precise timing.          Args:, AlignedSegment, Path, SentenceSegment

### Community 48 - "质量测试"
Cohesion: 0.22
Nodes (7): ASRBackend, ASR backend Protocol definition., Protocol for ASR backends.      Each backend receives a list of audio chunks and, Transcribe audio chunks into text segments.          Args:             chunks: L, Protocol, ASRSegment, Chunk

### Community 49 - "工程卫生"
Cohesion: 0.16
Nodes (12): load_sentences(), Align pipeline stage: sentences.jsonl → forced alignment → aligned.jsonl., Load SentenceSegments from JSONL., Write AlignedSegments to JSONL., Run align stage: load sentences → forced alignment → aligned.jsonl.      Args:, run_align(), write_aligned(), AlignedSegment (+4 more)

### Community 50 - "术语测试"
Cohesion: 0.25
Nodes (6): LLMBackend, LLM backend Protocol definition., Protocol for LLM cleaning backends.      Each backend receives pre-replaced segm, Clean transcription segments using LLM.          Rules:         - Do NOT change, CleanSegment, Glossary

### Community 51 - "媒体测试"
Cohesion: 0.25
Nodes (8): GlossaryReplacement, A deterministic string replacement rule., When no replacements match, text is unchanged., Replacements modify text and track applied rules., Case-insensitive matching., test_apply_replacements_basic(), test_apply_replacements_case_insensitive(), test_apply_replacements_no_match()

### Community 52 - "断句测试"
Cohesion: 0.16
Nodes (16): prepare_media(), Media processing: probe + audio extraction., Probe media info and extract audio to workspace.      Steps:     1. ffprobe -> M, Root configuration for Subtap., SubtapConfig, MediaInfo, Path, SubtapConfig (+8 more)

### Community 53 - "对齐后处理"
Cohesion: 0.29
Nodes (6): load_glossary(), Glossary loader and data model.  Supports YAML glossary files with: - terms: can, Load glossary from YAML file.      Returns empty Glossary if path is None or fil, Path, Loading with None path returns empty glossary., test_load_glossary_none()

### Community 54 - "LLM基础"
Cohesion: 0.29
Nodes (6): bad_aligned_jsonl(), empty_aligned_jsonl(), good_aligned_jsonl(), Tests for quality module — scorer, error_detector, fixer., Well-formed aligned segments., Aligned segments with various errors.

### Community 55 - "ASR基础"
Cohesion: 0.14
Nodes (11): OutputLifecycle, Output lifecycle management., Append to run log.          Args:             log_entry: Log entry dictionary, Finalize output, generate checksum.          Returns:             Dictionary wit, Manages output file writing lifecycle., Initialize output lifecycle.          Args:             version_dir: Version dir, Initialize output task., Write user-visible artifact.          Args:             name: File name (e.g., ' (+3 more)

### Community 56 - "对齐基础"
Cohesion: 0.22
Nodes (9): ModelDownloader, Download models (stub — real implementation needs model hosting)., SubtapConfig, Downloader returns path when model already present., Downloader raises NotImplementedError for missing models., Downloader raises ValueError for unknown model., test_downloader_download_exists(), test_downloader_download_not_implemented() (+1 more)

### Community 57 - "进度条"
Cohesion: 0.17
Nodes (11): ModelVerifier, Verify model integrity., Verify a model's files exist and are non-empty.          Returns dict with statu, Verifier reports missing when no files., Verifier reports ok when files present., Verifier reports corrupt when file is empty., Verifier returns unknown for unregistered model., test_verifier_corrupt() (+3 more)

### Community 58 - "TUI界面"
Cohesion: 0.33
Nodes (5): Logger, Path, Logging setup for Subtap., Configure file + console logging., setup_logging()

### Community 59 - "事件总线"
Cohesion: 0.40
Nodes (5): models, auto_download, root, workspace, keep_intermediate

### Community 61 - "状态持久化"
Cohesion: 0.12
Nodes (16): Phase 15 + 16：Output Engine 实现计划, 任务 10：完整集成测试, 任务 11：最终验证, 任务 1：创建输出异常定义, 任务 2：创建命名策略系统, 任务 3：创建输出生命周期控制, 任务 4：创建版本管理系统, 任务 5：创建 OutputEngine 核心 (+8 more)

### Community 83 - "Community 83"
Cohesion: 0.12
Nodes (15): TUI, cli.py, 📋 CLI 命令, 🔧 Pipeline 流程, Subtap, 🖥️ TUI 界面, 📦 安装, 🚀 快速开始 (+7 more)

### Community 84 - "Community 84"
Cohesion: 0.14
Nodes (12): ModelRegistry, Query model status across all registered models., List all available model names., Check if a model is installed and complete., Test listing available models., get_path returns correct directory., get_path raises ValueError for unknown model., is_available returns True when all files present. (+4 more)

### Community 85 - "Community 85"
Cohesion: 0.13
Nodes (8): OutputEngine, Finalize output, create latest link, cleanup old versions.          Returns:, Unified output management engine., Write final output file.          Args:             ext: File extension (e.g., ', Write report file.          Args:             content: Report content (markdown), Write metrics file.          Args:             metrics: Metrics dictionary, Append to run log.          Args:             log_entry: Log entry dictionary, Write intermediate artifacts.          Args:             artifacts: Dictionary o

### Community 86 - "Community 86"
Cohesion: 0.14
Nodes (8): NamingStrategy, Naming strategy for output files., Initialize naming strategy.          Args:             input_name: Input file na, Get final output file name.          Args:             ext: File extension (e.g., Get report file name.          Returns:             Report file name (e.g., 'vid, Get metrics file name.          Returns:             Metrics file name (e.g., 'v, Get artifact file name.          Args:             name: Artifact name (e.g., 'a, Manages output file naming conventions.

### Community 87 - "Community 87"
Cohesion: 0.14
Nodes (13): Phase 14: 安装与用户交付系统实现计划, 任务 1：重构 CLI 命令结构, 任务 2：创建 setup 业务逻辑模块, 任务 3：实现 setup 命令 - Step 1 系统检查, 任务 4：实现 setup 命令 - Step 3 模型安装, 任务 5：扩展模型管理 - list 和 remove 命令, 任务 6：增强 doctor 命令, 任务 7：集成测试 - 完整 setup 流程 (+5 more)

### Community 88 - "Community 88"
Cohesion: 0.20
Nodes (12): ASR后端, Aligner后端, LLM后端, align.py, asr.py, backends, clean.py, align (+4 more)

### Community 89 - "Community 89"
Cohesion: 0.18
Nodes (12): ffmpeg, pydub, 音频切段, 音频标准化, audio, channels, format, sample_rate (+4 more)

### Community 90 - "Community 90"
Cohesion: 0.27
Nodes (9): ModelRemover, Remove installed models., Remove a model directory.          Args:             model_name: Name of model t, Path, Test removing non-existent model directory returns False., Test removing unknown model raises ValueError., test_model_remover_not_exists(), test_model_remover_removes() (+1 more)

### Community 91 - "Community 91"
Cohesion: 0.25
Nodes (6): OutputError, Output system exceptions., Base exception for output system errors., Write intermediate artifacts.          Args:             artifacts: Dictionary o, Test OutputError is a proper exception., test_output_error_is_exception()

### Community 92 - "Community 92"
Cohesion: 0.15
Nodes (7): ModelStatus, Model management system: registry, download, verify., Download a model. Stub implementation raises.          Real implementation would, Status of a single model., Check status of all registered models., Get the directory path for a specific model., Path

### Community 93 - "Community 93"
Cohesion: 0.50
Nodes (4): ASS, SRT, TXT, 字幕导出

### Community 94 - "Community 94"
Cohesion: 0.50
Nodes (4): to_dict returns expected keys., to_dict returns expected keys., test_policy_to_dict(), test_stage_state_to_dict()

### Community 95 - "Community 95"
Cohesion: 0.67
Nodes (3): clean, glossary_path, style_rules

## Knowledge Gaps
- **128 isolated node(s):** `subtap`, `SentenceSegment`, `Path`, `AlignedSegment`, `Chunk` (+123 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **17 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `SubtapConfig` connect `断句测试` to `导出模块`, `分段处理`, `报告生成`, `HTTP ASR后端`, `媒体处理`, `管道控制`, `配置管理`, `状态管理`, `事件系统`, `ASR测试`, `LLM后端`, `替换规则`, `工作空间`, `日志系统`, `测试配置`, `工程卫生`, `对齐基础`, `进度条`, `Community 84`, `Community 90`, `Community 92`?**
  _High betweenness centrality (0.184) - this node is a cross-community bridge._
- **Why does `Path` connect `报告生成` to `VAD检测`, `Git防护`, `决策引擎`, `清洁室检查`, `管道控制`, `质量评分`, `质量修复`, `Community 84`, `对齐基础`, `进度条`, `Community 90`?**
  _High betweenness centrality (0.156) - this node is a cross-community bridge._
- **Why does `PipelineController` connect `管道控制` to `分段处理`, `工作空间`, `报告生成`, `测试配置`, `媒体处理`, `执行策略`, `工程卫生`, `断句测试`, `状态管理`, `分段测试`, `对齐测试`, `替换规则`?**
  _High betweenness centrality (0.088) - this node is a cross-community bridge._
- **Are the 64 inferred relationships involving `SubtapConfig` (e.g. with `ModelDownloader` and `ModelRegistry`) actually correct?**
  _`SubtapConfig` has 64 INFERRED edges - model-reasoned connections that need verification._
- **Are the 54 inferred relationships involving `Workspace` (e.g. with `Pipeline` and `SubtapConfig`) actually correct?**
  _`Workspace` has 54 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `PipelineController` (e.g. with `Workspace` and `EventLogger`) actually correct?**
  _`PipelineController` has 17 INFERRED edges - model-reasoned connections that need verification._
- **Are the 11 inferred relationships involving `Path` (e.g. with `ModelDownloader` and `ModelRegistry`) actually correct?**
  _`Path` has 11 INFERRED edges - model-reasoned connections that need verification._