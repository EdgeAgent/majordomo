"""Shared fixtures: a throwaway data dir and an offline runtime."""

from __future__ import annotations

from pathlib import Path

import pytest

from majordomo.config import Settings
from majordomo.providers import FakeProvider
from majordomo.runtime import Runtime, build_runtime


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", provider="fake")


@pytest.fixture()
def runtime(settings: Settings) -> Runtime:
    built = build_runtime(settings, provider=FakeProvider(), offline=True)
    yield built
    built.close()
