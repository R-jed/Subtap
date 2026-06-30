"""中文小句边界识别。

基于中文语法特点识别小句边界，用于字幕断句。
核心原则：从第一性原理出发，不针对特定素材调参，不堆补丁。
"""

from __future__ import annotations

from subtap.core.phrases import mark_phrase_boundaries

# 句末标点
_SENTENCE_END = set("。！？.!?")
# 逗号/分号
_COMMA = set("，、,;")
# 语气词
_PARTICLES = set("了呢吧啊嘛吗呀哦")
# 双字连词
_CONJ_PAIRS = {
    "但是",
    "所以",
    "因为",
    "而且",
    "不过",
    "可是",
    "然后",
    "或者",
    "如果",
    "虽然",
    "即使",
    "不仅",
    "而是",
    "于是",
    "因此",
    "那么",
    "这么",
    "怎么",
    "什么",
    "这个",
    "那个",
    "还是",
    "就是",
    "不是",
    "只有",
    "只要",
    "既然",
    "哪怕",
    "无论",
    "不管",
    "另外",
}
# 连词起始字（双字连词的第一个字）
_CONJ_STARTERS = {pair[0] for pair in _CONJ_PAIRS}


def identify_clause_boundaries(
    words: list[dict],
    marked: list[dict] | None = None,
    pause_threshold: float = 0.2,
) -> list[tuple[str, int] | None]:
    """识别每个词位置是否是小句边界。

    Args:
        words: 词列表，每个词是 {"word": str, "start_sec": float, "end_sec": float}
        marked: 标记了 phrase_role 的词列表（来自 mark_phrase_boundaries）
        pause_threshold: 停顿阈值（秒）

    Returns:
        与 words 等长的列表，每个元素是 (boundary_type, score) 或 None。
        boundary_type: "sentence_end" | "comma" | "pause" | "particle" | "conjunction"
        score: 0-100，越高越适合断句
    """
    if not words:
        return []

    if marked is None:
        marked = mark_phrase_boundaries(words)

    n = len(words)
    boundaries: list[tuple[str, int] | None] = [None] * n

    for i, w in enumerate(words):
        word = w["word"]
        role = marked[i].get("phrase_role") if i < len(marked) else None

        # 强边界：句末标点（不受保护区限制）
        if word in _SENTENCE_END:
            boundaries[i] = ("sentence_end", 100)
            continue

        # 强边界：逗号/分号（不受保护区限制）
        if word in _COMMA:
            boundaries[i] = ("comma", 80)
            continue

        # 中边界：连词起始（双字连词的第一个字，不受保护区限制）
        if word in _CONJ_STARTERS and i + 1 < n:
            pair = word + words[i + 1]["word"]
            if pair in _CONJ_PAIRS:
                boundaries[i] = ("conjunction", 55)
                continue

        # 跳过保护区内部（连词检测之后）
        if role == "phrase_mid":
            continue

        # 中边界：停顿
        if i > 0:
            gap = w["start_sec"] - words[i - 1]["end_sec"]
            if gap >= pause_threshold:
                boundaries[i] = ("pause", 60)
                continue

    # 语气词后标记（在语气词之后的位置）
    for i in range(n - 1):
        if words[i]["word"] in _PARTICLES:
            next_role = (
                marked[i + 1].get("phrase_role") if i + 1 < len(marked) else None
            )
            if next_role != "phrase_mid":
                if boundaries[i + 1] is None:
                    boundaries[i + 1] = ("particle", 50)

    return boundaries
