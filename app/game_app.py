from __future__ import annotations

from pathlib import Path

from textual.app import App

from app.screens import GameScreen, MainMenuScreen, LevelSelectScreen


class LedgerHeistApp(App[None]):
    TITLE = "The Ledger Heist"
    SUB_TITLE = "terminal ledger puzzles"
    CSS_PATH = Path(__file__).with_name("theme.tcss")
    SCREENS = {
        "menu": MainMenuScreen,
        "game": GameScreen,
        "level_select": LevelSelectScreen,
    }
    BINDINGS = [
        ("ctrl+c", "noop", "Blocked", False),
    ]

    def action_noop(self) -> None:
        pass

    def on_mount(self) -> None:
        self.push_screen("menu")
