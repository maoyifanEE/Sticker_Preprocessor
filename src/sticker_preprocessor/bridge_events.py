from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .bridge_contract import CONTRACT_VERSION, git_commit
from .runtime_paths import runtime_root


def bridge_runs_root() -> Path:
    return runtime_root() / "bridge-runs"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def prune_bridge_runs(days: int = 7) -> int:
    root = bridge_runs_root()
    root.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.now(UTC) - timedelta(days=days)
    removed = 0
    for child in root.iterdir():
        try:
            if not child.is_dir() or child.is_symlink():
                continue
            timestamp = datetime.fromtimestamp(child.stat().st_mtime, UTC)
            lock = child / ".running"
            if lock.exists() or timestamp >= cutoff:
                continue
            shutil.rmtree(child)
            removed += 1
        except Exception:
            continue
    return removed


class BridgeEventWriter:
    def __init__(self, path: Path, *, bridge_run_id: str | None, tool_run_id: str) -> None:
        self.path = path
        self.bridge_run_id = bridge_run_id
        self.tool_run_id = tool_run_id
        self.tool_commit = git_commit()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, **metrics: Any) -> None:
        record = {
            "timestamp": utc_now_iso(),
            "event": event,
            "bridgeRunId": self.bridge_run_id,
            "toolRunId": self.tool_run_id,
            "contractVersion": CONTRACT_VERSION,
            "toolCommit": self.tool_commit,
        }
        for key, value in metrics.items():
            if isinstance(value, Path):
                record[key] = value.name
            else:
                record[key] = value
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
