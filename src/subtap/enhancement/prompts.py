"""LLM prompts for subtitle enhancement tasks."""

from __future__ import annotations

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
    """Build prompt for specific enhancement task.

    Args:
        task: Task name (correction, glossary_correction, cleaning, segmentation, translation).
        text: Text to enhance.
        **kwargs: Additional task-specific parameters.

    Returns:
        Formatted prompt string.
    """
    if task not in TASK_PROMPTS:
        raise ValueError(f"Unknown task: {task}")

    template = TASK_PROMPTS[task]
    return template.format(text=text, **kwargs)
