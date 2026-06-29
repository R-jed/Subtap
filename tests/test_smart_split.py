"""Smart split based on word-level timestamps."""

from subtap.core.export import _smart_split


# ── Acceptance criteria tests (Task 3) ──


def test_de_structure_protection():
    """验收标准 1: '它实际市场售价都已经到万元' 不被拆开（的字结构保护）。"""
    text = "它实际市场售价都已经到万元"
    words = [
        {"word": ch, "start_sec": i * 0.2, "end_sec": (i + 1) * 0.2}
        for i, ch in enumerate(text)
    ]
    result = _smart_split(words, text, max_chars=25)
    # Should be a single line (all words in one phrase)
    assert len(result) == 1
    assert result[0]["text"] == text


def test_conjunction_pair_protection_1():
    """验收标准 2: '但是它一点都不便宜' 不被拆开（关联词对保护）。"""
    text = "但是它一点都不便宜"
    words = [
        {"word": ch, "start_sec": i * 0.2, "end_sec": (i + 1) * 0.2}
        for i, ch in enumerate(text)
    ]
    result = _smart_split(words, text, max_chars=25)
    assert len(result) == 1
    assert result[0]["text"] == text


def test_conjunction_pair_protection_2():
    """验收标准 3: '所以这台吉亚斯为什么这么贵' 不被拆开（关联词对保护）。"""
    text = "所以这台吉亚斯为什么这么贵"
    words = [
        {"word": ch, "start_sec": i * 0.2, "end_sec": (i + 1) * 0.2}
        for i, ch in enumerate(text)
    ]
    result = _smart_split(words, text, max_chars=25)
    assert len(result) == 1
    assert result[0]["text"] == text


def test_particle_break_after_le():
    """验收标准 4: '了很难原价买到' 中 '了' 是语气词，之后可断。"""
    text = "了很难原价买到"
    words = [
        {"word": ch, "start_sec": i * 0.2, "end_sec": (i + 1) * 0.2}
        for i, ch in enumerate(text)
    ]
    # With small max_chars, "了" (particle) should be a preferred break point
    result = _smart_split(words, text, max_chars=5)
    # "了" should be in the first line (not isolated)
    assert result[0]["text"].startswith("了")
    # Total text should be preserved
    total = "".join(r["text"] for r in result)
    assert total == text


def test_max_chars_force_split():
    """验收标准 5: 超过 max_chars 的行仍能被正确切分。"""
    text = "这是一段很长的文本需要被正确切分不能超过限制"
    words = [
        {"word": ch, "start_sec": i * 0.2, "end_sec": (i + 1) * 0.2}
        for i, ch in enumerate(text)
    ]
    result = _smart_split(words, text, max_chars=10)
    assert len(result) >= 2
    for line in result:
        assert len(line["text"]) <= 10
    # Total text preserved
    total = "".join(r["text"] for r in result)
    assert total == text


def test_output_format_unchanged():
    """输出格式不变: list[dict] with text/start_sec/end_sec."""
    words = [
        {"word": "你", "start_sec": 1.0, "end_sec": 1.2},
        {"word": "好", "start_sec": 1.2, "end_sec": 1.4},
    ]
    result = _smart_split(words, "你好", max_chars=20)
    assert isinstance(result, list)
    assert len(result) >= 1
    for line in result:
        assert "text" in line
        assert "start_sec" in line
        assert "end_sec" in line
        assert isinstance(line["text"], str)
        assert isinstance(line["start_sec"], float)
        assert isinstance(line["end_sec"], float)


def test_split_by_sentence_ending_punctuation():
    """句号/问号/叹号强制断句。"""
    words = [
        {"word": "你", "start_sec": 0.0, "end_sec": 0.2},
        {"word": "好", "start_sec": 0.2, "end_sec": 0.4},
        {"word": "。", "start_sec": 0.4, "end_sec": 0.4},
        {"word": "世", "start_sec": 0.5, "end_sec": 0.7},
        {"word": "界", "start_sec": 0.7, "end_sec": 0.9},
    ]
    result = _smart_split(words, "你好。世界", max_chars=20)
    assert len(result) == 2
    assert result[0]["text"] == "你好"
    assert result[1]["text"] == "世界"


def test_split_by_pause():
    """停顿 > threshold 且行长度 ≥ min_chars 时断句。"""
    words = [
        {"word": "这", "start_sec": 0.0, "end_sec": 0.2},
        {"word": "台", "start_sec": 0.2, "end_sec": 0.4},
        {"word": "相", "start_sec": 0.4, "end_sec": 0.6},
        {"word": "机", "start_sec": 0.6, "end_sec": 0.8},
        {"word": "从", "start_sec": 0.8, "end_sec": 1.0},
        {"word": "2015", "start_sec": 1.0, "end_sec": 1.5},
        {"word": "年", "start_sec": 1.5, "end_sec": 1.7},
        {"word": "发", "start_sec": 1.7, "end_sec": 1.9},
        {"word": "布", "start_sec": 1.9, "end_sec": 2.1},
        # 2.1s → 2.6s 间隔 0.5s > 0.3s 阈值
        {"word": "到", "start_sec": 2.6, "end_sec": 2.8},
        {"word": "今", "start_sec": 2.8, "end_sec": 3.0},
        {"word": "天", "start_sec": 3.0, "end_sec": 3.2},
    ]
    result = _smart_split(words, "这台相机从2015年发布到今天", max_chars=20, pause_threshold=0.3)
    assert len(result) == 2
    assert "发布" in result[0]["text"]
    assert "今天" in result[1]["text"]


def test_split_by_max_chars():
    """超过 max_chars 时强制断句。"""
    words = [
        {"word": f"字{i}", "start_sec": i * 0.1, "end_sec": (i + 1) * 0.1}
        for i in range(25)
    ]
    text = "".join(f"字{i}" for i in range(25))
    result = _smart_split(words, text, max_chars=20)
    for line in result:
        assert len(line["text"]) <= 20


def test_merge_short_fragments():
    """短碎片（< min_chars）合并到相邻行。"""
    words = [
        {"word": "这", "start_sec": 0.0, "end_sec": 0.2},
        {"word": "台", "start_sec": 0.2, "end_sec": 0.4},
        {"word": "相", "start_sec": 0.4, "end_sec": 0.6},
        {"word": "机", "start_sec": 0.6, "end_sec": 0.8},
        {"word": "。", "start_sec": 0.8, "end_sec": 0.8},
        {"word": "的", "start_sec": 1.0, "end_sec": 1.1},
    ]
    result = _smart_split(words, "这台相机。的", max_chars=20, min_chars=3)
    # "的" 只有 1 字，应合并到前一行
    assert len(result) == 1
    assert "的" in result[0]["text"]


def test_comma_split_when_line_full():
    """逗号 + 当前行已满时断句。"""
    words = [
        {"word": "这", "start_sec": 0.0, "end_sec": 0.2},
        {"word": "台", "start_sec": 0.2, "end_sec": 0.4},
        {"word": "相", "start_sec": 0.4, "end_sec": 0.6},
        {"word": "机", "start_sec": 0.6, "end_sec": 0.8},
        {"word": "从", "start_sec": 0.8, "end_sec": 1.0},
        {"word": "2015", "start_sec": 1.0, "end_sec": 1.5},
        {"word": "年", "start_sec": 1.5, "end_sec": 1.7},
        {"word": "发", "start_sec": 1.7, "end_sec": 1.9},
        {"word": "布", "start_sec": 1.9, "end_sec": 2.1},
        {"word": "，", "start_sec": 2.1, "end_sec": 2.1},
        {"word": "一", "start_sec": 2.3, "end_sec": 2.5},
        {"word": "直", "start_sec": 2.5, "end_sec": 2.7},
    ]
    result = _smart_split(words, "这台相机从2015年发布，一直", max_chars=20)
    assert len(result) >= 2


def test_time_from_word_timestamps():
    """断句时间应来自 word 时间戳，不是估算。"""
    words = [
        {"word": "你", "start_sec": 1.0, "end_sec": 1.2},
        {"word": "好", "start_sec": 1.2, "end_sec": 1.4},
        {"word": "。", "start_sec": 1.4, "end_sec": 1.4},
        {"word": "世", "start_sec": 2.0, "end_sec": 2.2},
        {"word": "界", "start_sec": 2.2, "end_sec": 2.4},
    ]
    result = _smart_split(words, "你好。世界", max_chars=20)
    assert result[0]["start_sec"] == 1.0
    assert result[0]["end_sec"] == 1.4
    assert result[1]["start_sec"] == 2.0
    assert result[1]["end_sec"] == 2.4
