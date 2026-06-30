"""Tests for script file loader."""

import pytest
from pathlib import Path
from subtap.script.loader import load_script, UnsupportedFormatError

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_txt():
    text = load_script(FIXTURES / "script_test_manuscript.txt")
    assert len(text) > 0
    assert "相机" in text


def test_load_srt():
    text = load_script(FIXTURES / "script_test_manuscript.srt")
    assert len(text) > 0
    # 不应包含 SRT 序号和时间轴
    assert "-->" not in text
    assert "00:00" not in text


def test_load_md():
    text = load_script(FIXTURES / "script_test_manuscript.md")
    assert len(text) > 0
    # 不应包含 Markdown 标记
    assert "# " not in text
    assert "**" not in text


def test_load_docx():
    text = load_script(FIXTURES / "script_test_manuscript.docx")
    assert len(text) > 0
    assert "相机" in text


def test_load_xlsx():
    text = load_script(FIXTURES / "script_test_manuscript.xlsx")
    assert len(text) > 0
    assert "相机" in text


def test_unsupported_format(tmp_path):
    # 创建一个存在的文件，但格式不支持
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_text("dummy content")
    with pytest.raises(UnsupportedFormatError, match="不支持"):
        load_script(pdf_file)
