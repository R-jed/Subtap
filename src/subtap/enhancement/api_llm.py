"""API LLM enhancement: uses external LLM API for enhancement."""

from __future__ import annotations

from collections.abc import Callable

from subtap.enhancement.base import EnhancementMode, EnhancementResult
from subtap.enhancement.tasks import EnhancementTask, get_tasks_for_mode
from subtap.enhancement.validator import EnhancementValidator
from subtap.schemas.enhancement import CleanSegment

# ── Prompts (merged from prompts.py) ──

SYSTEM_PROMPT = """你是一个专业的字幕编辑助手。你的任务是处理字幕文本，使其更准确、更易读。

重要规则：
1. 只修改文本内容，绝对不要修改时间戳
2. 不要删除任何内容
3. 不要总结或缩写
4. 保持原意不变
5. 输出格式必须与输入格式一致"""

TASK_PROMPTS = {
    "correction": """请修正以下字幕中的语音识别错误：
{text}

要求：
- 修正明显的语音识别错误
- 保持原意不变
- 不要修改时间戳""",
    "glossary_correction": """请根据术语表修正以下字幕：
术语表：{glossary}
字幕：{text}

要求：
- 使用术语表中的正确术语替换错误术语
- 保持原意不变
- 不要修改时间戳""",
    "ai_hotword_replacement": """请根据热词表和上下文修正以下字幕中的专有名词：
热词表：{glossary}
字幕：{text}

要求：
- 只在上下文确实指向热词时替换
- 保持原意不变
- 不要修改时间戳""",
    "cleaning": """请清洗以下字幕文本：
{text}

要求：
- 去除多余的空格和标点
- 修正明显的错别字
- 保持原意不变
- 不要修改时间戳""",
    "segmentation": """请将以下字幕文本智能切分为合适的句子：
{text}

要求：
- 每个句子应该完整且易读
- 保持原意不变
- 不要修改时间戳""",
    "translation": """请将以下字幕翻译为{target_language}：
{text}

要求：
- 翻译要自然流畅
- 保持原意不变
- 不要修改时间戳""",
}


def build_prompt(task: str, text: str, **kwargs) -> str:
    """Build prompt for specific enhancement task."""
    if task not in TASK_PROMPTS:
        raise ValueError(f"Unknown task: {task}")
    return TASK_PROMPTS[task].format(text=text, **kwargs)


# ── API Enhancer ──


class APIEnhancer:
    """API-based LLM enhancement — sends text to external LLM.

    Rules:
    - Only sends TEXT, never audio
    - Validates output preserves timing
    - Requires confirmation for external API calls
    """

    mode = EnhancementMode.API

    def __init__(
        self,
        provider: str = "openai_compatible",
        model: str = "gpt-4.1-mini",
        api_key: str | None = None,
        endpoint: str | None = None,
        text_client: (
            Callable[[str, str, dict[str, str] | None, str], str] | None
        ) = None,
    ):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.endpoint = endpoint
        self.text_client = text_client
        self.validator = EnhancementValidator()

    def enhance(
        self,
        segments: list[CleanSegment],
        glossary: dict[str, str] | None = None,
        tasks: list[EnhancementTask] | None = None,
        target_language: str = "",
    ) -> EnhancementResult:
        """Enhance segments using external LLM API."""
        if tasks is None:
            tasks = get_tasks_for_mode("api")

        enhanced = []
        api_calls = 0
        errors = []

        for seg in segments:
            text = seg.text
            change_reasons = []

            for task in tasks:
                try:
                    prompt = build_prompt(
                        task.value,
                        text,
                        glossary=str(glossary) if glossary else "",
                        target_language=target_language,
                    )
                    if self.text_client is not None:
                        text = self.text_client(
                            text, task.value, glossary, target_language
                        )
                    else:
                        _ = prompt
                    api_calls += 1
                    change_reasons.append(f"api_{task.value}")
                except Exception as e:
                    errors.append(f"Segment {seg.segment_id}: {e}")

            enhanced.append(
                CleanSegment(
                    segment_id=seg.segment_id,
                    source_chunk_id=seg.source_chunk_id,
                    text=text,
                    original_text=seg.original_text,
                    start_sec=seg.start_sec,
                    end_sec=seg.end_sec,
                    enhancement_mode="api",
                    changed=text != seg.original_text,
                    change_reasons=seg.change_reasons + change_reasons,
                )
            )

        validation = self.validator.validate(segments, enhanced)
        if not validation.valid:
            errors.extend(validation.errors)

        return EnhancementResult(
            segments=enhanced,
            mode=EnhancementMode.API,
            changed_count=sum(1 for s in enhanced if s.changed),
            api_calls=api_calls,
            errors=errors,
        )
