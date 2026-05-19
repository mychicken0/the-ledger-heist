from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_SAVE = {
    "last_level": 0,
    "cleared_levels": [],
    "best_scores": {},
}


def writable_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def save_path(path: Path | None = None) -> Path:
    return path or writable_root() / "saves" / "save.json"


def load_save(path: Path | None = None) -> dict[str, Any]:
    target = save_path(path)
    if not target.exists():
        save_game(DEFAULT_SAVE.copy(), target)
        return DEFAULT_SAVE.copy()

    try:
        with target.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (json.JSONDecodeError, OSError):
        payload = {}

    save_data = DEFAULT_SAVE.copy()
    if isinstance(payload, dict):
        save_data.update({
            "last_level": _coerce_int(payload.get("last_level"), 0),
            "cleared_levels": _coerce_list(payload.get("cleared_levels")),
            "best_scores": _coerce_dict(payload.get("best_scores")),
        })
    save_game(save_data, target)
    return save_data


def save_game(data: dict[str, Any], path: Path | None = None) -> None:
    target = save_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
        file.write("\n")


def _coerce_int(value: Any, default: int) -> int:
    return value if isinstance(value, int) and value >= 0 else default


def _coerce_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _coerce_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
