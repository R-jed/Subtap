"""ITN (Inverse Text Normalization) tests."""

from subtap.core.itn import chinese_to_num


def test_basic_digit_conversion():
    """中文数字转阿拉伯数字。"""
    assert chinese_to_num("二零一五") == "2015"


def test_year_month():
    """年月场景。"""
    assert chinese_to_num("2015年8月") == "2015年8月"


def test_decimal():
    """小数点转换。"""
    assert chinese_to_num("三点一四") == "3.14"


def test_large_number():
    """大数字：万级+千级尾数≥1000时转全数字。"""
    assert chinese_to_num("一万两千三百四十五") == "12345"
    assert chinese_to_num("一万两千九百九十九") == "12999"


def test_mixed_text():
    """混合文本中数字转换。"""
    result = chinese_to_num("这台相机从二零一五年八月发布")
    assert "2015" in result


def test_english_unchanged():
    """英文不转换。"""
    assert chinese_to_num("Hello World 123") == "Hello World 123"


def test_already_numeric():
    """已是数字不转换。"""
    assert chinese_to_num("价格是100元") == "价格是100元"


def test_empty_string():
    """空字符串。"""
    assert chinese_to_num("") == ""


def test_large_number_combo():
    """亿+万组合：一亿两千万。"""
    assert chinese_to_num("一亿两千万") == "1.2亿"


def test_large_number_wan():
    """万级：十二万。"""
    assert chinese_to_num("十二万") == "12万"
    # 万级+千级尾数为整千时保留万单位
    assert chinese_to_num("一万五千") == "1.5万"


def test_single_digit_not_converted():
    """单独的数字词（非数字语境）不转换。"""
    assert chinese_to_num("一直是一机难求") == "一直是一机难求"
    assert chinese_to_num("一点都不便宜") == "一点都不便宜"


def test_itn_approximate_shang():
    """上1000张 → 上千张（概数前缀）"""
    assert chinese_to_num("上1000张") == "上千张"


def test_itn_decimal_missing_dot():
    """06秒 → 0.6秒（小数点缺失）"""
    assert chinese_to_num("06秒") == "0.6秒"


def test_itn_approximate_context():
    """我们用他们拍了上1000张照片 → 上千张"""
    result = chinese_to_num("我们用他们拍了上1000张照片")
    assert "上千张" in result


# --- ITN 单位规范化 ---

def test_unit_mm():
    """毫米→mm"""
    assert chinese_to_num("二十八毫米") == "28mm"


def test_unit_cm():
    """厘米→cm"""
    assert chinese_to_num("二十厘米") == "20cm"


def test_unit_m():
    """米→m"""
    assert chinese_to_num("三千米") == "3000m"


def test_unit_g():
    """克→g"""
    assert chinese_to_num("一百克") == "100g"


def test_unit_yuan_kept():
    """元保持中文"""
    assert chinese_to_num("五十元") == "50元"


def test_unit_kuai_kept():
    """块保持中文"""
    assert chinese_to_num("两百块") == "200块"


def test_percent():
    """百分之五十→50%"""
    assert chinese_to_num("百分之五十") == "50%"
