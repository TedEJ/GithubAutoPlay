"""Snapshots in local-data/ (ignored by git: they hold real network data)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "local-data"
PREFIX = "snapshot-"


def load_latest(data_dir: Path = DEFAULT_DATA_DIR) -> dict | None:
    """The newest snapshot, or None. A broken file is ignored."""
    data_dir = Path(data_dir)
    if not data_dir.is_dir():
        return None
    for path in sorted(data_dir.glob(PREFIX + "*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            return data
    return None


def save(data: dict, generated: datetime, data_dir: Path = DEFAULT_DATA_DIR) -> Path:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / f"{PREFIX}{generated.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return path
