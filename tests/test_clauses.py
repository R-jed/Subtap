"""小句边界识别测试。"""

from subtap.core.clauses import identify_clause_boundaries


def _make_words(text):
    """将文本拆成单字符词列表。"""
    return [{"word": c, "start_sec": i * 0.2, "end_sec": (i + 1) * 0.2}
            for i, c in enumerate(text) if c.strip()]


def test_sentence_end_boundary():
    """句末标点是最强边界。"""
    words = _make_words("你好。世界")
    boundaries = identify_clause_boundaries(words)
    punct_idx = next(i for i, w in enumerate(words) if w["word"] == "。")
    assert boundaries[punct_idx] == ("sentence_end", 100)


def test_comma_boundary():
    """逗号是强边界。"""
    words = _make_words("这个问题，所以我们做")
    boundaries = identify_clause_boundaries(words)
    comma_idx = next(i for i, w in enumerate(words) if w["word"] == "，")
    assert boundaries[comma_idx] == ("comma", 80)


def test_pause_boundary():
    """停顿是中边界。"""
    words = [
        {"word": "这", "start_sec": 0.0, "end_sec": 0.2},
        {"word": "台", "start_sec": 0.2, "end_sec": 0.4},
        {"word": "相", "start_sec": 0.4, "end_sec": 0.6},
        {"word": "机", "start_sec": 0.6, "end_sec": 0.8},
        # 0.4s gap
        {"word": "从", "start_sec": 1.2, "end_sec": 1.4},
    ]
    boundaries = identify_clause_boundaries(words, pause_threshold=0.3)
    assert boundaries[4] == ("pause", 60)


def test_conjunction_boundary():
    """连词起始是中边界。"""
    words = _make_words("虽然贵但是值得")
    boundaries = identify_clause_boundaries(words)
    dan_idx = next(i for i, w in enumerate(words) if w["word"] == "但")
    assert boundaries[dan_idx][0] == "conjunction"


def test_protected_zone_no_boundary():
    """保护区内不标记边界。"""
    from subtap.core.phrases import mark_phrase_boundaries
    words = _make_words("它的传感器大")
    marked = mark_phrase_boundaries(words)
    boundaries = identify_clause_boundaries(words, marked)
    de_idx = next(i for i, w in enumerate(words) if w["word"] == "的")
    assert boundaries[de_idx] is None


def test_particle_boundary():
    """语气词后是好断点。"""
    words = _make_words("好了我们走")
    boundaries = identify_clause_boundaries(words)
    le_idx = next(i for i, w in enumerate(words) if w["word"] == "了")
    assert boundaries[le_idx + 1][0] == "particle"


def test_no_boundary_in_normal_text():
    """普通文本中没有边界。"""
    words = _make_words("相机")
    boundaries = identify_clause_boundaries(words)
    assert all(b is None for b in boundaries)
