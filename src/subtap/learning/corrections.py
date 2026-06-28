"""Explainable correction learning helpers."""

from __future__ import annotations


def learn_correction_pairs(
    draft_texts: list[str],
    corrected_texts: list[str],
) -> list[dict[str, str]]:
    """Extract changed subtitle lines as correction pairs."""
    pairs: list[dict[str, str]] = []
    for draft, corrected in zip(draft_texts, corrected_texts):
        if draft != corrected:
            pairs.append({"from": draft, "to": corrected})
    return pairs
