from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS = {
    "player_name": "operator",
    "theme": "dark_hacker",
    "log_limit": 300,
    "starting_level": 0,
}


def resource_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


def resource_path(*parts: str) -> Path:
    return resource_root().joinpath(*parts)


def load_levels(path: Path | None = None) -> list[dict[str, Any]]:
    level_path = path or resource_path("data", "levels.json")
    with level_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    levels = payload.get("levels") if isinstance(payload, dict) else payload
    if not isinstance(levels, list) or not levels:
        raise ValueError("levels.json must contain a non-empty levels list.")

    for index, level in enumerate(levels):
        _validate_level(index, level)
    return levels


def load_settings(path: Path | None = None) -> dict[str, Any]:
    settings_path = path or resource_path("data", "settings.json")
    if not settings_path.exists():
        return DEFAULT_SETTINGS.copy()

    with settings_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    settings = DEFAULT_SETTINGS.copy()
    if isinstance(payload, dict):
        settings.update(payload)
    return settings


def _validate_level(index: int, level: Any) -> None:
    required = {
        "id",
        "title",
        "briefing",
        "current_period",
        "open_periods",
        "closed_periods",
        "accounts",
        "objectives",
        "audit_limit",
        "command_limit",
        "rules",
    }
    if not isinstance(level, dict):
        raise ValueError(f"Level {index + 1} must be an object.")

    missing = sorted(required - level.keys())
    if missing:
        raise ValueError(f"Level {index + 1} is missing: {', '.join(missing)}.")

    if not isinstance(level["accounts"], list) or not level["accounts"]:
        raise ValueError(f"Level {index + 1} accounts must be a non-empty list.")
    seen_accounts: set[str] = set()
    for account in level["accounts"]:
        if not isinstance(account, dict):
            raise ValueError(f"Level {index + 1} accounts must contain objects.")
        for key in ("name", "type", "normal_side", "balance", "locked"):
            if key not in account:
                raise ValueError(f"Level {index + 1} account is missing {key}.")
        name = str(account["name"]).lower()
        if not name:
            raise ValueError(f"Level {index + 1} account name cannot be empty.")
        if name in seen_accounts:
            raise ValueError(f"Level {index + 1} has duplicate account {name}.")
        seen_accounts.add(name)
        if not isinstance(account["balance"], int):
            raise ValueError(f"Level {index + 1} account balances must be integers.")
        if str(account["normal_side"]).lower() not in {"debit", "credit"}:
            raise ValueError(f"Level {index + 1} account normal side must be debit or credit.")

    for key in ("audit_limit", "command_limit"):
        if not isinstance(level[key], int) or level[key] < 0:
            raise ValueError(f"Level {index + 1} {key} must be a nonnegative integer.")

    if not isinstance(level["current_period"], str) or not level["current_period"]:
        raise ValueError(f"Level {index + 1} current_period must be a string.")
    if not isinstance(level["open_periods"], list) or not all(isinstance(period, str) for period in level["open_periods"]):
        raise ValueError(f"Level {index + 1} open_periods must be a list of strings.")
    if not isinstance(level["closed_periods"], list) or not all(isinstance(period, str) for period in level["closed_periods"]):
        raise ValueError(f"Level {index + 1} closed_periods must be a list of strings.")
    if not isinstance(level["objectives"], dict):
        raise ValueError(f"Level {index + 1} objectives must be an object.")
    if not isinstance(level["rules"], list) or not all(isinstance(rule, str) for rule in level["rules"]):
        raise ValueError(f"Level {index + 1} rules must be a list of strings.")
    documents = level.get("documents", [])
    if documents is not None and not isinstance(documents, list):
        raise ValueError(f"Level {index + 1} documents must be a list.")
    for document in documents:
        if not isinstance(document, dict):
            raise ValueError(f"Level {index + 1} documents must contain objects.")
        for key in ("id", "type", "amount", "period", "description"):
            if key not in document:
                raise ValueError(f"Level {index + 1} document is missing {key}.")
        if not isinstance(document["amount"], int) or document["amount"] < 0:
            raise ValueError(f"Level {index + 1} document amount must be a nonnegative integer.")
