"""Tests for user-owned resource initialization."""

from subtap.core.user_resources import ensure_default_glossary


def test_ensure_default_glossary_preserves_existing_content(tmp_path):
    glossary = tmp_path / "glossaries" / "default.yaml"
    glossary.parent.mkdir(parents=True)
    glossary.write_text("理光GR4=李光机亚四\n", encoding="utf-8")

    result = ensure_default_glossary(tmp_path)

    assert result == glossary
    assert glossary.read_text(encoding="utf-8") == "理光GR4=李光机亚四\n"
