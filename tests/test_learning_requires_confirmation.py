"""Phase 26: learning confirmation gate."""

from subtap.learning.profile_store import ProfileStore


def test_learning_requires_confirmation(tmp_path):
    """Automatic profile writes must be blocked unless user confirms."""
    store = ProfileStore(tmp_path / "profile")

    applied = store.apply_corrections(
        [{"from": "错词", "to": "正确词"}],
        confirmed=False,
    )

    assert applied is False
    assert store.list_corrections() == []

    applied = store.apply_corrections(
        [{"from": "错词", "to": "正确词"}],
        confirmed=True,
    )
    assert applied is True
    assert store.list_corrections() == [{"from": "错词", "to": "正确词"}]
