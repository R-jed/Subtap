"""Tests for packaging.homebrew.evaluate — carrier selection by fixed rules."""

from packaging.homebrew.evaluate import select


def result(name, *, cold=True, hidden=True, rollback=True, audit=True, size=100):
    return {
        "carrier": name,
        "cold_install": cold,
        "python_hidden": hidden,
        "rollback": rollback,
        "audit": audit,
        "installed_bytes": size,
    }


def test_rejects_carrier_that_fails_a_mandatory_gate():
    assert select([result("formula", audit=False), result("cask")]) == "cask"


def test_prefers_no_python_knowledge_before_smaller_size():
    assert select([result("formula", hidden=False, size=10), result("cask", size=100)]) == "cask"


def test_prefers_rollback_before_smaller_size():
    assert select([result("formula", rollback=False, size=10), result("cask", size=100)]) == "cask"


def test_returns_no_selection_when_all_carriers_fail():
    assert select([result("formula", cold=False), result("cask", audit=False)]) is None
