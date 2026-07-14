"""Tests for script aligner."""

import pytest
from subtap.script.aligner import (
    align_sequences,
    compute_alignment_quality,
    AlignmentQualityError,
)


def test_equal_sequences():
    ops = align_sequences(["A", "B", "C"], ["A", "B", "C"])
    assert all(op.op == "equal" for op in ops)


def test_replace():
    ops = align_sequences(["A", "B"], ["A", "X"])
    replace_ops = [op for op in ops if op.op == "replace"]
    assert len(replace_ops) == 1
    assert replace_ops[0].asr_idx == 1
    assert replace_ops[0].ref_idx == 1


def test_insert():
    ops = align_sequences(["A", "B"], ["A", "X", "B"])
    insert_ops = [op for op in ops if op.op == "insert"]
    assert len(insert_ops) == 1


def test_delete():
    ops = align_sequences(["A", "B", "C"], ["A", "C"])
    delete_ops = [op for op in ops if op.op == "delete"]
    assert len(delete_ops) == 1


def test_mixed_operations():
    ops = align_sequences(["A", "B", "C"], ["A", "X", "D", "C"])
    ops_list = [op.op for op in ops]
    assert "equal" in ops_list
    assert "replace" in ops_list or "insert" in ops_list


def test_quality_perfect():
    ops = align_sequences(["A", "B"], ["A", "B"])
    q = compute_alignment_quality(ops, ["A", "B"], ["A", "B"])
    assert q == 1.0


def test_quality_low_raises():
    asr = ["完全不同的句子A", "完全不同的句子B", "完全不同的句子C"]
    ref = ["X", "Y", "Z"]
    ops = align_sequences(asr, ref)
    with pytest.raises(AlignmentQualityError, match="差异过大"):
        compute_alignment_quality(ops, asr, ref)
