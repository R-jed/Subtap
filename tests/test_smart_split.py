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


# ── Task 3b acceptance criteria ──


def test_so_yi_not_split():
    """验收标准 1: '搭配镜头比它大了这么多所以是比它好的' — '所以' 不被拆开。"""
    text = "搭配镜头比它大了这么多所以是比它好的"
    words = [
        {"word": ch, "start_sec": i * 0.15, "end_sec": (i + 1) * 0.15}
        for i, ch in enumerate(text)
    ]
    result = _smart_split(words, text, max_chars=15)
    total = "".join(r["text"] for r in result)
    assert total == text
    # "所以" should not be split across lines
    for line in result:
        # No line should end with "所" alone (without "以" following)
        assert not line["text"].endswith("所"), f"'所以' was split: {result}"


def test_wo_men_merged():
    """验收标准 2: '我们' 不独立成行（合并到相邻行）。

    Scenario: pause-based split creates "我们" as a 2-char orphan fragment.
    With <=2 merge, it should be merged back into the previous line.
    """
    words = [
        {"word": "这", "start_sec": 0.0, "end_sec": 0.2},
        {"word": "台", "start_sec": 0.2, "end_sec": 0.4},
        {"word": "相", "start_sec": 0.4, "end_sec": 0.6},
        {"word": "机", "start_sec": 0.6, "end_sec": 0.8},
        # pause > 0.2 threshold → triggers split
        {"word": "我", "start_sec": 1.2, "end_sec": 1.3},
        {"word": "们", "start_sec": 1.3, "end_sec": 1.4},
    ]
    result = _smart_split(words, "这台相机我们", max_chars=20, min_chars=3)
    total = "".join(r["text"] for r in result)
    assert total == "这台相机我们"
    # "我们" should NOT be a standalone line (merged back into previous)
    for line in result:
        assert line["text"] != "我们", f"'我们' is standalone: {result}"


def test_na_hai_merged():
    """验收标准 3: '那还' 不独立成行（合并到相邻行）。

    Scenario: pause-based split creates "那还" as a 2-char orphan fragment.
    With <=2 merge, it should be merged back into the previous line.
    """
    words = [
        {"word": "这", "start_sec": 0.0, "end_sec": 0.2},
        {"word": "台", "start_sec": 0.2, "end_sec": 0.4},
        {"word": "相", "start_sec": 0.4, "end_sec": 0.6},
        {"word": "机", "start_sec": 0.6, "end_sec": 0.8},
        # pause > 0.2 threshold → triggers split
        {"word": "那", "start_sec": 1.2, "end_sec": 1.3},
        {"word": "还", "start_sec": 1.3, "end_sec": 1.4},
    ]
    result = _smart_split(words, "这台相机那还", max_chars=20, min_chars=3)
    total = "".join(r["text"] for r in result)
    assert total == "这台相机那还"
    # "那还" should NOT be a standalone line (merged back into previous)
    for line in result:
        assert line["text"] != "那还", f"'那还' is standalone: {result}"


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


# ── Task 2: 行尾拖字修复 ──


def test_no_trailing_conjunction():
    """行尾不应出现连词"""
    words = [
        {"word": "相机", "start_sec": 0.0, "end_sec": 0.5},
        {"word": "但是", "start_sec": 0.5, "end_sec": 1.0},
        {"word": "轻便", "start_sec": 1.0, "end_sec": 1.5},
    ]
    result = _smart_split(words, "相机但是轻便", max_chars=10)
    for line in result:
        assert not line["text"].endswith("但是"), f"行尾出现连词: {line['text']}"


def test_no_trailing_pronoun():
    """行尾不应出现代词（我们/它能/它还）"""
    words = [
        {"word": "愿意买呢", "start_sec": 0.0, "end_sec": 1.0},
        {"word": "我们", "start_sec": 1.0, "end_sec": 1.5},
        {"word": "这次", "start_sec": 1.5, "end_sec": 2.0},
    ]
    result = _smart_split(words, "愿意买呢我们这次", max_chars=10)
    for line in result:
        assert not line["text"].endswith("我们"), f"行尾出现代词: {line['text']}"


def test_no_trailing_particle():
    """行尾不应出现语气词（呃/呢/啊/呀）"""
    words = [
        {"word": "做工", "start_sec": 0.0, "end_sec": 0.5},
        {"word": "呃", "start_sec": 0.5, "end_sec": 0.8},
        {"word": "我觉得", "start_sec": 0.8, "end_sec": 1.5},
    ]
    result = _smart_split(words, "做工呃我觉得", max_chars=10)
    for line in result:
        assert not line["text"].endswith("呃"), f"行尾出现语气词: {line['text']}"


def test_no_trailing_demonstrative():
    """行尾不应出现指示词（这个/那个/那这）"""
    words = [
        {"word": "单品", "start_sec": 0.0, "end_sec": 0.5},
        {"word": "这个", "start_sec": 0.5, "end_sec": 1.0},
        {"word": "iPhonePocket", "start_sec": 1.0, "end_sec": 2.0},
    ]
    result = _smart_split(words, "单品这个iPhonePocket", max_chars=15)
    for line in result:
        assert not line["text"].endswith("这个"), f"行尾出现指示词: {line['text']}"


def test_conjunction_not_at_line_end():
    """验收标准 (Task 3c-1): '但是' 不应留在行尾，应移到下一行开头。

    Scenario: pause-based split triggers after '但是' has been accumulated.
    The conjunction should be stripped from line end and prepended to next line.
    """
    words = [
        {"word": "是", "start_sec": 0.0, "end_sec": 0.2},
        {"word": "我", "start_sec": 0.2, "end_sec": 0.4},
        {"word": "见", "start_sec": 0.4, "end_sec": 0.6},
        {"word": "过", "start_sec": 0.6, "end_sec": 0.8},
        {"word": "开", "start_sec": 0.8, "end_sec": 1.0},
        {"word": "机", "start_sec": 1.0, "end_sec": 1.2},
        {"word": "速", "start_sec": 1.2, "end_sec": 1.4},
        {"word": "度", "start_sec": 1.4, "end_sec": 1.6},
        {"word": "最", "start_sec": 1.6, "end_sec": 1.8},
        {"word": "快", "start_sec": 1.8, "end_sec": 2.0},
        {"word": "的", "start_sec": 2.0, "end_sec": 2.2},
        {"word": "相", "start_sec": 2.2, "end_sec": 2.4},
        {"word": "机", "start_sec": 2.4, "end_sec": 2.6},
        # Pause > 0.2 threshold before "但是"
        {"word": "但", "start_sec": 3.0, "end_sec": 3.2},
        {"word": "是", "start_sec": 3.2, "end_sec": 3.4},
        # Another pause before the rest
        {"word": "轻", "start_sec": 3.8, "end_sec": 4.0},
        {"word": "便", "start_sec": 4.0, "end_sec": 4.2},
    ]
    result = _smart_split(
        words, "是我见过开机速度最快的相机但是轻便",
        max_chars=25, min_chars=5, pause_threshold=0.2,
    )
    total = "".join(r["text"] for r in result)
    assert total == "是我见过开机速度最快的相机但是轻便"
    # "但是" should NOT be at the end of any line
    for line in result:
        assert not line["text"].endswith("但是"), (
            f"'但是' at line end: {result}"
        )
    # "但是" should be at the start of a line
    assert any(line["text"].startswith("但是") for line in result), (
        f"'但是' not at any line start: {result}"
    )


def test_so_yi_not_split_realistic():
    """验收标准 (Task 3c-2): '所以' 不被拆开 — realistic scenario with pause.

    Text: '搭配镜头比它大了这么多所以是比它好的没它小'
    With max_chars=15, '所以' should NOT be split across lines.
    """
    text = "搭配镜头比它大了这么多所以是比它好的没它小"
    words = [
        {"word": ch, "start_sec": i * 0.15, "end_sec": (i + 1) * 0.15}
        for i, ch in enumerate(text)
    ]
    result = _smart_split(words, text, max_chars=15)
    total = "".join(r["text"] for r in result)
    assert total == text
    # "所以" should not be split: no line ends with "所" alone
    for line in result:
        assert not line["text"].endswith("所"), f"'所以' was split: {result}"


def test_conjunction_fragment_merged():
    """连词碎片（所以/并且/现在/同时）应合并到相邻行，不被 ends_punct 阻断。"""
    words = [
        {"word": "这", "start_sec": 0.0, "end_sec": 0.2},
        {"word": "个", "start_sec": 0.2, "end_sec": 0.4},
        {"word": "问", "start_sec": 0.4, "end_sec": 0.6},
        {"word": "题", "start_sec": 0.6, "end_sec": 0.8},
        {"word": "，", "start_sec": 0.8, "end_sec": 0.8},
        # pause gap 0.5s
        {"word": "所", "start_sec": 1.3, "end_sec": 1.5},
        {"word": "以", "start_sec": 1.5, "end_sec": 1.7},
        {"word": "我", "start_sec": 1.8, "end_sec": 2.0},
        {"word": "们", "start_sec": 2.0, "end_sec": 2.2},
        {"word": "要", "start_sec": 2.2, "end_sec": 2.4},
        {"word": "做", "start_sec": 2.4, "end_sec": 2.6},
    ]
    result = _smart_split(words, "这个问题，所以我们要做", max_chars=25)
    # "所以" 不应独立成行
    for line in result:
        assert line["text"].strip() != "所以", f"'所以' 不应独立成行: {result}"


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


def test_single_conjunction_stripped_from_line_end():
    """单字连词（因/则/但/所/以）应从行尾剥离。

    模拟 #209 场景: pause 在单字连词之后触发拆分，使连词落在行尾。
    当前 _CONJ_ENDINGS 只有双字连词，单字连词如 '但' 不会被剥离。
    """
    words = [
        {"word": "这", "start_sec": 0.0, "end_sec": 0.2},
        {"word": "台", "start_sec": 0.2, "end_sec": 0.4},
        {"word": "相", "start_sec": 0.4, "end_sec": 0.6},
        {"word": "机", "start_sec": 0.6, "end_sec": 0.8},
        {"word": "很", "start_sec": 0.8, "end_sec": 1.0},
        {"word": "好", "start_sec": 1.0, "end_sec": 1.2},
        {"word": "用", "start_sec": 1.2, "end_sec": 1.4},
        {"word": "但", "start_sec": 1.4, "end_sec": 1.6},
        # pause gap 1.0s > 0.3s threshold → triggers split after "但"
        {"word": "价", "start_sec": 2.6, "end_sec": 2.8},
        {"word": "格", "start_sec": 2.8, "end_sec": 3.0},
        {"word": "太", "start_sec": 3.0, "end_sec": 3.2},
        {"word": "贵", "start_sec": 3.2, "end_sec": 3.4},
    ]
    result = _smart_split(
        words, "这台相机很好用但价格太贵",
        max_chars=20, min_chars=3, pause_threshold=0.3,
    )
    total = "".join(r["text"] for r in result)
    assert total == "这台相机很好用但价格太贵"
    assert len(result) >= 2, f"应有拆分，但只有 {len(result)} 行: {result}"
    # "但" 不应留在行尾，应被剥离到下一行开头
    for line in result[:-1]:
        txt = line["text"]
        assert not txt.endswith("但"), f"行尾不应有孤立的 '但': {txt}"


# ── Task 2: 基于小句边界重构 _smart_split ──


def test_clause_based_split_no_fragments():
    """基于小句边界断句不应产生碎片。"""
    words = [
        {"word": "这", "start_sec": 0.0, "end_sec": 0.2},
        {"word": "个", "start_sec": 0.2, "end_sec": 0.4},
        {"word": "问", "start_sec": 0.4, "end_sec": 0.6},
        {"word": "题", "start_sec": 0.6, "end_sec": 0.8},
        {"word": "，", "start_sec": 0.8, "end_sec": 0.8},
        {"word": "所", "start_sec": 1.3, "end_sec": 1.5},
        {"word": "以", "start_sec": 1.5, "end_sec": 1.7},
        {"word": "我", "start_sec": 1.8, "end_sec": 2.0},
        {"word": "们", "start_sec": 2.0, "end_sec": 2.2},
        {"word": "要", "start_sec": 2.2, "end_sec": 2.4},
        {"word": "做", "start_sec": 2.4, "end_sec": 2.6},
    ]
    result = _smart_split(words, "这个问题，所以我们要做", max_chars=25)
    for line in result:
        assert line["text"].strip() != "所以", f"'所以' 不应独立成行: {result}"


def test_clause_based_split_conjunction_pair():
    """关联词对在小句边界处正确断开。"""
    words = [
        {"word": "虽", "start_sec": 0.0, "end_sec": 0.2},
        {"word": "然", "start_sec": 0.2, "end_sec": 0.4},
        {"word": "贵", "start_sec": 0.4, "end_sec": 0.6},
        {"word": "，", "start_sec": 0.6, "end_sec": 0.6},
        {"word": "但", "start_sec": 0.8, "end_sec": 1.0},
        {"word": "是", "start_sec": 1.0, "end_sec": 1.2},
        {"word": "值", "start_sec": 1.2, "end_sec": 1.4},
        {"word": "得", "start_sec": 1.4, "end_sec": 1.6},
    ]
    result = _smart_split(words, "虽然贵，但是值得", max_chars=25)
    for line in result:
        assert not line["text"].endswith("但"), f"行尾不应有孤立的 '但': {line['text']}"


def test_clause_based_split_long_sentence():
    """长小句不被过度拆分。"""
    words = [
        {"word": "我", "start_sec": 0.0, "end_sec": 0.2},
        {"word": "必", "start_sec": 0.2, "end_sec": 0.4},
        {"word": "须", "start_sec": 0.4, "end_sec": 0.6},
        {"word": "得", "start_sec": 0.6, "end_sec": 0.8},
        {"word": "先", "start_sec": 0.8, "end_sec": 1.0},
        {"word": "强", "start_sec": 1.0, "end_sec": 1.2},
        {"word": "调", "start_sec": 1.2, "end_sec": 1.4},
        {"word": "这", "start_sec": 1.4, "end_sec": 1.6},
        {"word": "个", "start_sec": 1.6, "end_sec": 1.8},
        {"word": "视", "start_sec": 1.8, "end_sec": 2.0},
        {"word": "频", "start_sec": 2.0, "end_sec": 2.2},
        {"word": "我", "start_sec": 2.2, "end_sec": 2.4},
        {"word": "绝", "start_sec": 2.4, "end_sec": 2.6},
        {"word": "对", "start_sec": 2.6, "end_sec": 2.8},
        {"word": "不", "start_sec": 2.8, "end_sec": 3.0},
        {"word": "是", "start_sec": 3.0, "end_sec": 3.2},
        {"word": "广", "start_sec": 3.2, "end_sec": 3.4},
        {"word": "告", "start_sec": 3.4, "end_sec": 3.6},
    ]
    result = _smart_split(words, "我必须得先强调这个视频我绝对不是广告", max_chars=25)
    assert len(result) == 1


def test_clause_boundary_driven_split():
    """验证小句边界驱动断句：断句位置应与小句边界一致。"""
    from subtap.core.clauses import identify_clause_boundaries

    words = [
        {"word": "这", "start_sec": 0.0, "end_sec": 0.2},
        {"word": "个", "start_sec": 0.2, "end_sec": 0.4},
        {"word": "问", "start_sec": 0.4, "end_sec": 0.6},
        {"word": "题", "start_sec": 0.6, "end_sec": 0.8},
        {"word": "，", "start_sec": 0.8, "end_sec": 0.8},
        {"word": "所", "start_sec": 1.3, "end_sec": 1.5},
        {"word": "以", "start_sec": 1.5, "end_sec": 1.7},
        {"word": "我", "start_sec": 1.8, "end_sec": 2.0},
        {"word": "们", "start_sec": 2.0, "end_sec": 2.2},
        {"word": "要", "start_sec": 2.2, "end_sec": 2.4},
        {"word": "做", "start_sec": 2.4, "end_sec": 2.6},
    ]
    text = "这个问题，所以我们要做"

    # 获取小句边界
    boundaries = identify_clause_boundaries(words)
    boundary_positions = [i for i, b in enumerate(boundaries) if b is not None]

    # 执行断句
    result = _smart_split(words, text, max_chars=25)

    # 验证断句位置与小句边界一致
    # 小句边界应该在位置 4 (逗号) 和位置 5 (所以)
    assert 4 in boundary_positions, "逗号应该是小句边界"
    assert 5 in boundary_positions, "'所' 应该是小句边界（连词起始）"

    # 验证断句结果：逗号后应该断句，但"所以"不应独立成行
    assert len(result) >= 2, f"逗号后应该断句: {result}"
    for line in result:
        assert line["text"].strip() != "所以", f"'所以' 不应独立成行: {result}"


# ── Task 3: 跨行断词修复 ──


def test_no_split_word_across_lines():
    """不应将词语切断跨行（如虚化→虚/化）"""
    # 构造一个场景，使"虚化"被拆分到两行
    # 核心的点是这个虚化的照片 - 总长度15字符
    # 设置 max_chars=8，迫使在"虚"和"化"之间断行
    words = [
        {"word": "核心的点是这个", "start_sec": 0.0, "end_sec": 2.0},
        {"word": "虚", "start_sec": 2.0, "end_sec": 2.2},
        {"word": "化", "start_sec": 2.2, "end_sec": 2.5},
        {"word": "的照片", "start_sec": 2.5, "end_sec": 3.0},
    ]
    result = _smart_split(words, "核心的点是这个虚化的照片", max_chars=8)
    # "虚化" 不应被拆分到两行
    all_text = "".join(line["text"] for line in result)
    # 检查没有单独的"虚"在行尾或单独的"化"在行首
    for i, line in enumerate(result):
        txt = line["text"]
        # 如果行尾是"虚"，检查下一行是否以"化"开头（这表示被拆分了）
        if txt.endswith("虚") and i + 1 < len(result):
            next_txt = result[i + 1]["text"]
            if next_txt.startswith("化"):
                # 这是一个断词错误，应该失败
                assert False, f"虚化被拆分到两行: '{txt}' | '{next_txt}'"


def test_no_split_number_unit():
    """不应将数字+单位切断（如二十八→二/八）"""
    words = [
        {"word": "都是", "start_sec": 0.0, "end_sec": 0.5},
        {"word": "二", "start_sec": 0.5, "end_sec": 0.7},
        {"word": "八毫米", "start_sec": 0.7, "end_sec": 1.2},
        {"word": "的", "start_sec": 1.2, "end_sec": 1.3},
    ]
    result = _smart_split(words, "都是二八毫米的", max_chars=10)
    # "二八毫米" 不应被拆分
    all_text = "".join(line["text"] for line in result)
    assert "二八毫米" in all_text, f"二八毫米被拆分: {result}"
