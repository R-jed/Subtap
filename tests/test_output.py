"""Tests for output system."""

import pytest
from subtap.output.exceptions import OutputError


def test_output_error_is_exception():
    """Test OutputError is a proper exception."""
    error = OutputError("test error")
    assert isinstance(error, Exception)
    assert str(error) == "test error"
