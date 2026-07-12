from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def repo_runtime_tmp(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = Path(__file__).resolve().parents[1]
    runtime = repo / ".runtime"
    temp = runtime / "test-temp"
    model = runtime / "models" / "rembg"
    temp.mkdir(parents=True, exist_ok=True)
    model.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TMP", str(temp))
    monkeypatch.setenv("TEMP", str(temp))
    monkeypatch.setenv("TMPDIR", str(temp))
    monkeypatch.setenv("U2NET_HOME", str(model))
