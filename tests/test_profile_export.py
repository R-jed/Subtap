"""Phase 26: profile export."""

import yaml

from subtap.learning.profile_store import ProfileStore


def test_profile_export(tmp_path):
    """Profile export should collect editable YAML profile files."""
    store = ProfileStore(tmp_path / "profile")
    store.add_glossary_replacement("错词", "正确词")

    export_path = store.export(tmp_path / "profile-export.yaml")
    payload = yaml.safe_load(export_path.read_text(encoding="utf-8"))

    assert payload["glossary"]["replacements"][0]["find"] == "错词"
    assert "corrections" in payload
    assert "segmentation_preferences" in payload
    assert "translation_terms" in payload
