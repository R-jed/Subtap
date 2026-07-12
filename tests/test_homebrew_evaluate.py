"""Tests for packaging.homebrew.evaluate — carrier selection by fixed rules."""

import json
import sys
from pathlib import Path
from unittest import mock

from packaging.homebrew.evaluate import main, select


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


def test_tiebreak_prefers_formula_over_cask():
    assert select([result("cask", size=100), result("formula", size=100)]) == "formula"


def test_select_does_not_mutate_input_list():
    original = [result("cask", size=200), result("formula", size=100)]
    snapshot = list(original)
    select(original)
    assert original == snapshot


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------

def _write_result(tmp_path: Path, name: str, **overrides) -> Path:
    """Write a carrier result JSON file and return its path."""
    data = result(name, **overrides)
    p = tmp_path / f"{name}.json"
    p.write_text(json.dumps(data))
    return p


def test_cli_json_output_structure(tmp_path):
    formula = _write_result(tmp_path, "formula")
    cask = _write_result(tmp_path, "cask")

    captured = {}
    with mock.patch("sys.stdout") as mock_stdout:
        mock_stdout.write = lambda s: captured.setdefault("lines", []).append(s)
        try:
            main([str(formula), str(cask)])
        except SystemExit:
            pass

    full_output = "".join(captured.get("lines", []))
    data = json.loads(full_output)
    assert data["selected"] == "formula"
    assert "formula" in data["qualified"]
    assert "cask" in data["qualified"]


def test_cli_print_selected_path(tmp_path, capsys):
    formula = _write_result(tmp_path, "formula")
    cask = _write_result(tmp_path, "cask")

    main(["--print-selected-path", str(formula), str(cask)])

    out = capsys.readouterr().out
    lines = out.strip().split("\n")
    # Last line should be the path to the selected carrier's file
    assert lines[-1] == str(formula)


def test_cli_exit_code_1_when_no_carrier_qualifies(tmp_path):
    formula = _write_result(tmp_path, "formula", cold=False)
    cask = _write_result(tmp_path, "cask", audit=False)

    with mock.patch("sys.exit") as mock_exit:
        main([str(formula), str(cask)])
        mock_exit.assert_called_once_with(1)
