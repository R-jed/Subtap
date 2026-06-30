"""Tests for script formatter."""
from subtap.script.formatter import format_script


def test_removes_hash_comments():
    text = "# 注释\n正文一\n# 又是注释\n正文二"
    assert format_script(text) == ["正文一", "正文二"]


def test_removes_slash_comments():
    text = "// 注释\n正文一\n正文二"
    assert format_script(text) == ["正文一", "正文二"]


def test_removes_bracket_notes():
    text = "【备注：内容】\n正文\n[说明：内容]"
    assert format_script(text) == ["正文"]


def test_removes_empty_lines():
    text = "正文一\n\n\n\n正文二"
    assert format_script(text) == ["正文一", "正文二"]


def test_strips_whitespace():
    text = "  正文一  \n\t正文二\t"
    assert format_script(text) == ["正文一", "正文二"]


def test_preserves_content_lines():
    text = "第一行\n第二行\n第三行"
    assert format_script(text) == ["第一行", "第二行", "第三行"]


def test_normalizes_fullwidth_comma():
    text = "你好，世界"
    result = format_script(text)
    assert result == ["你好，世界"]  # 中文语境保留全角


def test_with_real_fixture():
    from pathlib import Path
    fixture = Path(__file__).parent / "fixtures" / "script_test_manuscript.txt"
    lines = format_script(fixture.read_text(encoding="utf-8"))
    assert len(lines) > 0
    # 不应包含注释行
    for line in lines:
        assert not line.startswith("#")
        assert not line.startswith("//")
