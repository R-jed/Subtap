# tests/test_theme.py
import os
from subtap.ui.theme import Theme, get_display_width, truncate_by_width


class TestThemeColors:
    def test_default_theme_has_all_colors(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        t = Theme()
        assert t.GREEN != ""
        assert t.BLUE != ""
        assert t.CYAN != ""
        assert t.YELLOW != ""
        assert t.PURPLE != ""
        assert t.PURPLE_BOLD != ""
        assert t.RED != ""
        assert t.GRAY != ""
        assert t.NC != ""

    def test_no_color_disables_all(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        t = Theme()
        assert t.GREEN == ""
        assert t.BLUE == ""
        assert t.CYAN == ""
        assert t.YELLOW == ""
        assert t.PURPLE == ""
        assert t.RED == ""
        assert t.GRAY == ""

    def test_empty_no_color_keeps_colors(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "")
        t = Theme()
        assert t.GREEN != ""


class TestColorizeSize:
    def test_gb_is_red(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        t = Theme()
        result = t.colorize_size("1.5GB")
        assert t.RED in result
        assert "1.5GB" in result

    def test_mb_is_yellow(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        t = Theme()
        result = t.colorize_size("769MB")
        assert t.YELLOW in result

    def test_kb_is_green(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        t = Theme()
        result = t.colorize_size("12KB")
        assert t.GREEN in result

    def test_b_is_gray(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        t = Theme()
        result = t.colorize_size("512B")
        assert t.GRAY in result


class TestCJKWidth:
    def test_ascii_width(self):
        assert get_display_width("hello") == 5

    def test_cjk_width(self):
        assert get_display_width("你好") == 4

    def test_mixed_width(self):
        assert get_display_width("hi你好") == 6

    def test_emoji_zwj_width(self):
        assert get_display_width("‍️") == 0

    def test_truncate_ascii(self):
        result = truncate_by_width("hello world", 8)
        assert get_display_width(result) <= 8

    def test_truncate_cjk(self):
        result = truncate_by_width("你好世界欢迎光临", 8)
        assert get_display_width(result) <= 8
