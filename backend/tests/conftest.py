"""Shared pytest fixtures for backend tests."""
from __future__ import annotations

import pytest

from app.safety.layer import SafetyLayer


@pytest.fixture
def safety() -> SafetyLayer:
    return SafetyLayer()
