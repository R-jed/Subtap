"""语法短语边界识别模块。

识别中文文本中不可拆分的语法结构，返回短语边界标记。
用于 Smart Split 断句时判断哪些位置可以断开、哪些不可以。
"""

from __future__ import annotations

# 的/得/地 —— 作为短语核心标记
_DE_MARKERS = {"的", "得", "地"}

# 语气词（仅在词列表末尾时标记为 particle）
_PARTICLES = {"了", "呢", "吧", "啊", "嘛", "吗", "呀"}

# 的字结构右扫描边界：常见副词/助动词，通常是新谓语的开始
_DE_RIGHT_BOUNDARIES = {
    "很",
    "就",
    "都",
    "才",
    "又",
    "再",
    "已",
    "曾",
    "还",
    "更",
    "最",
    "太",
    "真",
    "挺",
    "蛮",
    "也",
    "不",
    "会",
    "能",
    "可",
    "要",
    "该",
}

# 标点符号
_PUNCTUATION = set("，。！？、；：…—,.!?;")

# 关联词对: (前词, 后词)
_CONJ_PAIRS: list[tuple[str, str]] = [
    ("虽然", "但是"),
    ("因为", "所以"),
    ("不仅", "而且"),
    ("即使", "也"),
    ("只要", "就"),
    ("既然", "就"),
    ("不但", "而且"),
    ("无论", "都"),
    ("不管", "都"),
    ("不论", "都"),
    ("如果", "就"),
    ("尽管", "但"),
    ("不是", "而是"),
    ("与其", "不如"),
]


def mark_phrase_boundaries(words: list[dict]) -> list[dict]:
    """标记词列表中的语法短语边界。

    Args:
        words: 词列表，每个词是 {"word": str, "start_sec": float, "end_sec": float}

    Returns:
        词列表（新列表），每个词增加 "phrase_role" 字段:
        - "phrase_start": 短语开始
        - "phrase_mid": 短语中间（不可在此断开）
        - "phrase_end": 短语结束
        - "particle": 语气词（之后是好断点）
        - None: 普通词
    """
    if not words:
        return []

    result = [{**w, "phrase_role": None} for w in words]
    n = len(result)

    # ── 1. 语气词标记（仅末尾） ──────────────────────────
    if n > 0 and result[-1]["word"] in _PARTICLES:
        result[-1]["phrase_role"] = "particle"

    # ── 2. 关联词对（先处理，有明确边界） ─────────────────
    for first, second in _CONJ_PAIRS:
        _mark_conjunction_pair(result, first, second)

    # ── 3. 的/得/地 短语结构 ─────────────────────────────
    for i, w in enumerate(result):
        ch = w["word"]
        if ch not in _DE_MARKERS:
            continue

        # 的/得/地 在词列表末尾时跳过 —— 结构助词后面必须有补语/中心词
        # 例如 "值得" 中的 "得" 是词素，不是结构助词
        if i == n - 1:
            continue

        # 向左扫描修饰语/动词/状语
        left = i
        while left > 0:
            prev = left - 1
            prev_ch = result[prev]["word"]
            if prev_ch in _DE_MARKERS:
                break
            if prev_ch in _PARTICLES:
                break
            if prev_ch in _PUNCTUATION:
                break
            if result[prev]["phrase_role"] in ("phrase_start", "phrase_mid"):
                break
            left = prev

        # 向右扫描中心词/补语/动词
        # 的字结构：在标点、语气词、常见副词/助动词处停止
        # 得字结构：仅在标点、语气词处停止（补语可包含否定词等）
        right = i
        while right < n - 1:
            nxt = right + 1
            nxt_ch = result[nxt]["word"]
            if nxt_ch in _DE_MARKERS:
                break
            if nxt_ch in _PARTICLES:
                break
            if nxt_ch in _PUNCTUATION:
                break
            if result[nxt]["phrase_role"] in ("phrase_mid", "phrase_end"):
                break
            # 的/地 结构在常见副词/助动词处停止
            if ch in ("的", "地") and nxt_ch in _DE_RIGHT_BOUNDARIES:
                break
            right = nxt

        # 标记短语角色
        if left < right:
            result[left]["phrase_role"] = "phrase_start"
            for j in range(left + 1, right + 1):
                result[j]["phrase_role"] = "phrase_mid" if j < right else "phrase_end"

    return result


def _mark_conjunction_pair(result: list[dict], first: str, second: str) -> None:
    """在词列表中标记一对关联词及其间的短语。"""
    n = len(result)
    first_len = len(first)
    second_len = len(second)

    # 找所有 first 的位置
    i = 0
    while i <= n - first_len:
        if _seq_match(result, i, first):
            first_start = i
            first_end = i + first_len - 1

            # 从 first 之后找 second
            j = first_end + 1
            while j <= n - second_len:
                if _seq_match(result, j, second):
                    second_start = j
                    second_end = j + second_len - 1

                    # 向右扩展到短语末尾
                    # 遇到标点/语气词停止
                    # 遇到的/得/地时：如果后面有内容则停止（结构助词），
                    # 如果是词末尾则继续（词素，如"值得"）
                    tail_end = second_end
                    while tail_end < n - 1:
                        nxt = tail_end + 1
                        nxt_ch = result[nxt]["word"]
                        if nxt_ch in _PUNCTUATION:
                            break
                        if nxt_ch in _PARTICLES:
                            break
                        if nxt_ch in _DE_MARKERS and nxt < n - 1:
                            # 的/得/地 后面有内容 → 结构助词，停止
                            # 的/得/地 在词列表末尾 → 词素，继续
                            break
                        if result[nxt]["phrase_role"] in ("phrase_mid", "phrase_end"):
                            break
                        tail_end = nxt

                    # 标记 first 为 phrase_start
                    for k in range(first_start, first_end + 1):
                        if result[k]["phrase_role"] is None:
                            result[k]["phrase_role"] = "phrase_start"

                    # 标记 first 和 second 之间为 phrase_mid
                    for k in range(first_end + 1, second_start):
                        if result[k]["phrase_role"] is None:
                            result[k]["phrase_role"] = "phrase_mid"

                    # 标记 second 为 phrase_mid
                    for k in range(second_start, second_end + 1):
                        if result[k]["phrase_role"] is None:
                            result[k]["phrase_role"] = "phrase_mid"

                    # 标记 second 之后到 tail_end 为 phrase_end
                    for k in range(second_end + 1, tail_end + 1):
                        if result[k]["phrase_role"] is None:
                            result[k]["phrase_role"] = "phrase_end"

                    i = tail_end + 1
                    break
                j += 1
            else:
                i += 1
        else:
            i += 1


def _seq_match(result: list[dict], start: int, text: str) -> bool:
    """检查词列表从 start 开始是否连续匹配 text 中的字符。"""
    if start + len(text) > len(result):
        return False
    for k, ch in enumerate(text):
        if result[start + k]["word"] != ch:
            return False
    return True
