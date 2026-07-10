"""Verify modules still import correctly after unused-import cleanup."""

import importlib


def test_export_module_imports():
    mod = importlib.import_module("subtap.core.export")
    assert hasattr(mod, "run_export")


def test_clean_module_imports():
    mod = importlib.import_module("subtap.core.clean")
    assert hasattr(mod, "load_asr_segments")


def test_hotword_module_imports():
    mod = importlib.import_module("subtap.glossary.hotword")
    assert hasattr(mod, "HotwordGlossary")


def test_tui_module_imports():
    mod = importlib.import_module("subtap.ui.tui")
    assert hasattr(mod, "BaseRunner")
