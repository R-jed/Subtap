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
    """大数字。"""
    assert chinese_to_num("一万两千三百四十五") == "12345"


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
    assert chinese_to_num("一亿两千万") == "120000000"


def test_large_number_wan():
    """万级：十二万。"""
    assert chinese_to_num("十二万") == "120000"
