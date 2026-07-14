"""tests for subtap.core.phrases — 语法短语边界识别"""

from __future__ import annotations


from subtap.core.phrases import mark_phrase_boundaries


def _make_words(text: str) -> list[dict]:
    """将文本拆成单字符词列表，模拟 forced aligner 输出。"""
    words = []
    for i, ch in enumerate(text):
        words.append({"word": ch, "start_sec": float(i), "end_sec": float(i + 1)})
    return words


def _roles(result: list[dict]) -> list[str | None]:
    """提取 phrase_role 列表，便于断言。"""
    return [w.get("phrase_role") for w in result]


# ── 的字结构 ──────────────────────────────────────────────


class TestDeGeStructure:
    """的字结构: [修饰语] + 的 + [中心词]"""

    def test_basic_de_ge(self):
        """ "它的传感器" → 它(phrase_start), 的(phrase_mid), 传(phrase_mid), 感(phrase_mid), 器(phrase_end)"""
        words = _make_words("它的传感器")
        result = mark_phrase_boundaries(words)
        roles = _roles(result)
        assert roles[0] == "phrase_start"  # 它
        assert roles[1] == "phrase_mid"  # 的
        assert roles[2] == "phrase_mid"  # 传
        assert roles[3] == "phrase_mid"  # 感
        assert roles[4] == "phrase_end"  # 器

    def test_de_ge_with_adj(self):
        """ "黑白的照片" → 黑(phrase_start), 白(phrase_mid), 的(phrase_mid), 照(phrase_mid), 片(phrase_end)"""
        words = _make_words("黑白的照片")
        result = mark_phrase_boundaries(words)
        roles = _roles(result)
        assert roles[0] == "phrase_start"  # 黑
        assert roles[1] == "phrase_mid"  # 白
        assert roles[2] == "phrase_mid"  # 的
        assert roles[3] == "phrase_mid"  # 照
        assert roles[4] == "phrase_end"  # 片

    def test_de_ge_boundary_scan(self):
        """的字结构应该向前扫描修饰语、向后扫描中心词。"""
        words = _make_words("红色的苹果很好吃")
        result = mark_phrase_boundaries(words)
        roles = _roles(result)
        # 红(phrase_start), 色(phrase_mid), 的(phrase_mid), 苹(phrase_mid), 果(phrase_end)
        assert roles[0] == "phrase_start"
        assert roles[1] == "phrase_mid"
        assert roles[2] == "phrase_mid"
        assert roles[3] == "phrase_mid"
        assert roles[4] == "phrase_end"
        # 很好吃 普通词
        assert roles[5] is None
        assert roles[6] is None
        assert roles[7] is None


# ── 得字结构 ──────────────────────────────────────────────


class TestDeDeStructure:
    """得字结构: [动词] + 得 + [补语]"""

    def test_basic_de_de(self):
        """ "觉得还不错" → 觉(phrase_start), 得(phrase_mid), 还(phrase_mid), 不(phrase_mid), 错(phrase_end)"""
        words = _make_words("觉得还不错")
        result = mark_phrase_boundaries(words)
        roles = _roles(result)
        assert roles[0] == "phrase_start"  # 觉
        assert roles[1] == "phrase_mid"  # 得
        assert roles[2] == "phrase_mid"  # 还
        assert roles[3] == "phrase_mid"  # 不
        assert roles[4] == "phrase_end"  # 错

    def test_de_de_short(self):
        """ "拍得好" → 拍(phrase_start), 得(phrase_mid), 好(phrase_end)"""
        words = _make_words("拍得好")
        result = mark_phrase_boundaries(words)
        roles = _roles(result)
        assert roles[0] == "phrase_start"
        assert roles[1] == "phrase_mid"
        assert roles[2] == "phrase_end"


# ── 地字结构 ──────────────────────────────────────────────


class TestDeDiStructure:
    """地字结构: [状语] + 地 + [动词]"""

    def test_basic_de_di(self):
        """ "轻松地拍摄" → 轻(phrase_start), 松(phrase_mid), 地(phrase_mid), 拍(phrase_mid), 摄(phrase_end)"""
        words = _make_words("轻松地拍摄")
        result = mark_phrase_boundaries(words)
        roles = _roles(result)
        assert roles[0] == "phrase_start"  # 轻
        assert roles[1] == "phrase_mid"  # 松
        assert roles[2] == "phrase_mid"  # 地
        assert roles[3] == "phrase_mid"  # 拍
        assert roles[4] == "phrase_end"  # 摄

    def test_de_di_single_char_adverb(self):
        """ "慢慢地走" → 慢(phrase_start), 慢(phrase_mid), 地(phrase_mid), 走(phrase_end)"""
        words = _make_words("慢慢地走")
        result = mark_phrase_boundaries(words)
        roles = _roles(result)
        assert roles[0] == "phrase_start"
        assert roles[1] == "phrase_mid"
        assert roles[2] == "phrase_mid"
        assert roles[3] == "phrase_end"


# ── 关联词对 ──────────────────────────────────────────────


class TestConjunctionPairs:
    """关联词对: 虽然...但是 / 因为...所以 / 不仅...而且 / 即使...也 / 只要...就"""

    def test_ranhou_danshi(self):
        """ "虽然贵但是值得" → 虽然(phrase_start), 贵(phrase_mid), 但是(phrase_mid), 值得(phrase_end)"""
        words = _make_words("虽然贵但是值得")
        result = mark_phrase_boundaries(words)
        roles = _roles(result)
        assert roles[0] == "phrase_start"  # 虽
        assert roles[1] == "phrase_start"  # 然
        assert roles[2] == "phrase_mid"  # 贵
        assert roles[3] == "phrase_mid"  # 但
        assert roles[4] == "phrase_mid"  # 是
        assert roles[5] == "phrase_end"  # 值
        assert roles[6] == "phrase_end"  # 得

    def test_yinwei_suoyi(self):
        """ "因为下雨所以迟到" → 因为(phrase_start), 下(phrase_mid), 雨(phrase_mid), 所以(phrase_mid), 迟(phrase_end), 到(phrase_end)"""
        words = _make_words("因为下雨所以迟到")
        result = mark_phrase_boundaries(words)
        roles = _roles(result)
        assert roles[0] == "phrase_start"  # 因
        assert roles[1] == "phrase_start"  # 为
        assert roles[2] == "phrase_mid"  # 下
        assert roles[3] == "phrase_mid"  # 雨
        assert roles[4] == "phrase_mid"  # 所
        assert roles[5] == "phrase_mid"  # 以
        assert roles[6] == "phrase_end"  # 迟
        assert roles[7] == "phrase_end"  # 到

    def test_jishi_ye(self):
        """ "即使失败也要试" → 即使(phrase_start), 失(phrase_mid), 败(phrase_mid), 也(phrase_mid), 要(phrase_end), 试(phrase_end)"""
        words = _make_words("即使失败也要试")
        result = mark_phrase_boundaries(words)
        roles = _roles(result)
        assert roles[0] == "phrase_start"  # 即
        assert roles[1] == "phrase_start"  # 使
        assert roles[2] == "phrase_mid"  # 失
        assert roles[3] == "phrase_mid"  # 败
        assert roles[4] == "phrase_mid"  # 也
        assert roles[5] == "phrase_end"  # 要
        assert roles[6] == "phrase_end"  # 试

    def test_zhiyao_jiu(self):
        """ "只要努力就行" → 只要(phrase_start), 努(phrase_mid), 力(phrase_mid), 就(phrase_mid), 行(phrase_end)"""
        words = _make_words("只要努力就行")
        result = mark_phrase_boundaries(words)
        roles = _roles(result)
        assert roles[0] == "phrase_start"  # 只
        assert roles[1] == "phrase_start"  # 要
        assert roles[2] == "phrase_mid"  # 努
        assert roles[3] == "phrase_mid"  # 力
        assert roles[4] == "phrase_mid"  # 就
        assert roles[5] == "phrase_end"  # 行


# ── 语气词 ──────────────────────────────────────────────


class TestParticles:
    """语气词尾: 了/呢/吧/啊/嘛/吗/呀"""

    def test_le_particle(self):
        """ "好了" → 好(None), 了(particle)"""
        words = _make_words("好了")
        result = mark_phrase_boundaries(words)
        roles = _roles(result)
        assert roles[0] is None
        assert roles[1] == "particle"

    def test_ne_particle(self):
        """ "走呢" → 走(None), 呢(particle)"""
        words = _make_words("走呢")
        result = mark_phrase_boundaries(words)
        roles = _roles(result)
        assert roles[0] is None
        assert roles[1] == "particle"

    def test_ba_particle(self):
        """ "好吧" → 好(None), 吧(particle)"""
        words = _make_words("好吧")
        result = mark_phrase_boundaries(words)
        roles = _roles(result)
        assert roles[0] is None
        assert roles[1] == "particle"

    def test_ma_particle(self):
        """ "对吗" → 对(None), 吗(particle)"""
        words = _make_words("对吗")
        result = mark_phrase_boundaries(words)
        roles = _roles(result)
        assert roles[0] is None
        assert roles[1] == "particle"

    def test_particle_at_end(self):
        """语气词不在末尾时不标记为 particle。"""
        words = _make_words("了不起")
        result = mark_phrase_boundaries(words)
        roles = _roles(result)
        # 了 在开头，不是语气词尾
        assert roles[0] is None
        assert roles[1] is None
        assert roles[2] is None


# ── 普通词 ──────────────────────────────────────────────


class TestPlainWords:
    """普通词不标记。"""

    def test_plain_word(self):
        """ "相机" → 相机(None)"""
        words = _make_words("相机")
        result = mark_phrase_boundaries(words)
        roles = _roles(result)
        assert roles[0] is None
        assert roles[1] is None

    def test_empty_list(self):
        """空列表返回空列表。"""
        result = mark_phrase_boundaries([])
        assert result == []

    def test_single_char(self):
        """单字无特殊标记。"""
        words = _make_words("好")
        result = mark_phrase_boundaries(words)
        roles = _roles(result)
        assert roles[0] is None


# ── 混合场景 ──────────────────────────────────────────────


class TestMixedScenarios:
    """混合场景：多种结构共存。"""

    def test_de_ge_then_particle(self):
        """ "它的好了" → 它(phrase_start), 的(phrase_mid), 好(phrase_end/particle冲突), 了(particle)"""
        words = _make_words("它的好了")
        result = mark_phrase_boundaries(words)
        roles = _roles(result)
        # 的字结构: 它→的→好
        assert roles[0] == "phrase_start"  # 它
        assert roles[1] == "phrase_mid"  # 的
        # 好 同时是 的字结构的 phrase_end 和 了 前的普通词
        # 语气词优先级更高，好 作为 的字结构的中心词结束
        assert roles[2] == "phrase_end"  # 好
        assert roles[3] == "particle"  # 了

    def test_preserves_original_fields(self):
        """返回结果保留原始字段。"""
        words = _make_words("好了")
        result = mark_phrase_boundaries(words)
        for w in result:
            assert "word" in w
            assert "start_sec" in w
            assert "end_sec" in w
            assert "phrase_role" in w

    def test_does_not_mutate_input(self):
        """不修改输入列表。"""
        words = _make_words("它的传感器")
        original_len = len(words)
        mark_phrase_boundaries(words)
        assert len(words) == original_len
        # 原始词没有 phrase_role
        for w in words:
            assert "phrase_role" not in w
