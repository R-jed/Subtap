"""Phase 26: editable glossary profile store."""

from subtap.learning.profile_store import ProfileStore


def test_glossary_store_add_list_remove(tmp_path):
    """Glossary profile should be readable YAML and removable."""
    store = ProfileStore(tmp_path / "profile")

    store.add_glossary_replacement("错词", "正确词")
    assert store.list_glossary_replacements() == [{"find": "错词", "replace": "正确词"}]

    removed = store.remove_glossary_replacement("错词")
    assert removed is True
    assert store.list_glossary_replacements() == []
    assert (tmp_path / "profile" / "glossary.yaml").exists()
