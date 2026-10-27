from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any


DEFAULT_STATE = {
    "contacts": {"next_page": 1, "processed": 0},
    "labels": {"label_index": 0, "next_page": 1, "processed": 0},
}


class SyncStateStore:
    def __init__(self, path: str | None = None) -> None:
        default_path = Path.cwd() / ".sync_state.json"
        self.path = Path(path or os.getenv("DOMANI_SYNC_STATE_PATH") or default_path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return deepcopy(DEFAULT_STATE)
        return self._merge_defaults(json.loads(self.path.read_text()))

    def save(self, state: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2))

    def reset(self) -> dict[str, Any]:
        state = deepcopy(DEFAULT_STATE)
        self.save(state)
        return state

    def _merge_defaults(self, loaded: dict[str, Any]) -> dict[str, Any]:
        merged = deepcopy(DEFAULT_STATE)
        for key, value in loaded.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key].update(value)
            else:
                merged[key] = value
        return merged
