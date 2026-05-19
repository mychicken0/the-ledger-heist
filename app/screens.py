from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Static, Tree, ListView, ListItem

from app.widgets import (
    AccountingPanel,
    AuditLogPanel,
    JournalEntriesPanel,
    StatusPanel,
    MissionBriefingPanel,
    DocumentViewerPanel,
    FileSystemPanel,
)
from game.commands import CommandProcessor
from game.engine import GameEngine
from game.level_loader import load_settings, load_levels
from game.save_system import load_save, save_game


class MainMenuScreen(Screen[None]):
    BINDINGS = [
        ("enter", "start_game", "Start"),
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Container(
            Static("THE LEDGER HEIST", id="menu-title", markup=False),
            Static(
                "Accounting puzzles for terminal operators.\n"
                "Post balanced journal entries, review trial balances, and pass the audit.",
                id="menu-copy",
                markup=False,
            ),
            Horizontal(
                Button("Start", id="start", variant="success"),
                Button("Select Level", id="select-level", variant="primary"),
                Button("Quit", id="quit", variant="error"),
                id="menu-actions",
            ),
            id="menu-root",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start":
            self.action_start_game()
        elif event.button.id == "select-level":
            self.app.switch_screen("level_select")
        elif event.button.id == "quit":
            self.app.exit()

    def action_start_game(self) -> None:
        self.app.switch_screen("game")


class GameScreen(Screen[None]):
    AUTO_FOCUS = "#command-input"
    BINDINGS = [
        ("ctrl+r", "restart_level", "Restart"),
        ("ctrl+l", "level_select", "Level Select"),
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.settings = load_settings()
        self.log_limit = int(self.settings.get("log_limit", 12))
        self.engine = GameEngine()
        self.processor = CommandProcessor(self.engine)
        self.log_lines: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Container(
            Horizontal(
                MissionBriefingPanel(id="briefing-panel"),
                DocumentViewerPanel(id="document-panel"),
                id="top-row",
            ),
            Horizontal(
                Container(
                    Horizontal(
                        AccountingPanel(id="accounting-panel"),
                        JournalEntriesPanel(id="journal-panel"),
                        id="ledger-row",
                    ),
                    AuditLogPanel(id="audit-log"),
                    id="left-pane",
                ),
                Container(
                    FileSystemPanel(id="filesystem-panel"),
                    StatusPanel(id="status-panel"),
                    id="right-pane",
                ),
                id="main-pane",
            ),
            Input(
                placeholder="command: docs, inspect inv-410, attach inv-410 JE-0001",
                id="command-input",
            ),
            id="game-root",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._log("System online. Type 'help' for command syntax.")
        self._refresh()
        self.query_one("#command-input", Input).focus()

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        label = str(event.node.label).strip()
        
        parts = []
        curr = event.node
        fs_panel = self.query_one("#filesystem-panel", FileSystemPanel)
        while curr and curr != fs_panel.root:
            curr_label = str(curr.label).strip()
            if curr_label.startswith("[DIR] ") or curr_label.startswith("[DOC] ") or curr_label.startswith("[TXT] "):
                parts.append(curr_label[6:])
            else:
                parts.append(curr_label)
            curr = curr.parent

        path = "/" + "/".join(reversed(parts))

        if label.startswith("[DIR] "):
            self._log(f"> cd {path}")
            result = self.processor.execute(f"cd {path}")
        else:
            self._log(f"> cat {path}")
            result = self.processor.execute(f"cat {path}")
            
        self._log(result.message)
        self._refresh()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "command-input":
            return
        command = event.value.strip()
        event.input.value = ""
        if command:
            self._log(f"> {command}")

        if command.lower() in {"level", "levels", "select", "menu"}:
            self._log("Opening level selector...")
            self.app.switch_screen("level_select")
            return

        result = self.processor.execute(command)
        self._log(result.message)
        self._refresh()

        if result.should_exit:
            self.app.exit()
            return
        self.query_one("#command-input", Input).focus()
        
        # force log to scroll to the end on every submit
        audit_log = self.query_one("#audit-log", AuditLogPanel)
        audit_log.scroll_end(animate=False)

    def action_restart_level(self) -> None:
        result = self.processor.execute("restart")
        self._log("> restart")
        self._log(result.message)
        self._refresh()

    def action_level_select(self) -> None:
        self.app.switch_screen("level_select")

    def _log(self, message: str) -> None:
        for line in message.splitlines():
            self.log_lines.append(line)
        self.log_lines = self.log_lines[-self.log_limit :]

    def _refresh(self) -> None:
        view = self.engine.get_view()
        
        for p in self.query("#briefing-panel"):
            p.update_view(view)
        for p in self.query("#document-panel"):
            p.update_view(view, self.engine.active_file)
        for p in self.query("#accounting-panel"):
            p.update_view(view)
        for p in self.query("#journal-panel"):
            p.update_view(view)
        for p in self.query("#status-panel"):
            p.update_view(view)
        for p in self.query("#filesystem-panel"):
            p.update_vfs(self.engine.vfs)
        for p in self.query("#audit-log"):
            p.update_log(self.log_lines)
        
        prompt_path = self.engine.vfs.get_path_string()
        for inp in self.query("#command-input"):
            inp.placeholder = f"operator@{prompt_path} $ (try 'help' or click files)"


class LevelSelectScreen(Screen[None]):
    AUTO_FOCUS = "#level-list"
    
    BINDINGS = [
        ("escape", "back", "Back"),
        ("q", "back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        list_pane = Container(
            ListView(id="level-list"),
            id="level-list-pane",
        )
        list_pane.border_title = "MISSIONS"
        
        details_pane = Container(
            Static(id="level-details", markup=True),
            id="level-details-pane",
        )
        details_pane.border_title = "MISSION BRIEFING & DETAILS"
        
        yield Container(
            Static("SELECT MISSION", id="level-select-title", markup=False),
            Horizontal(
                list_pane,
                details_pane,
                id="level-select-grid",
            ),
            Horizontal(
                Button("Launch Mission", id="launch", variant="success"),
                Button("Back to Menu", id="back", variant="default"),
                id="level-select-actions",
            ),
            id="level-select-root",
        )
        yield Footer()

    def on_show(self) -> None:
        self.refresh_levels()

    def refresh_levels(self) -> None:
        self.levels = load_levels()
        self.save_data = load_save()
        self.cleared = self.save_data.get("cleared_levels", [])
        
        list_view = self.query_one("#level-list", ListView)
        # Clear ListView safely
        for child in list(list_view.children):
            child.remove()
            
        for idx, lvl in enumerate(self.levels):
            lvl_id = lvl["id"]
            title = lvl["title"]
            
            # Determine status
            if lvl_id in self.cleared:
                status_str = "[CLEAR]"
                best_scores = self.save_data.get("best_scores", {})
                score = best_scores.get(lvl_id)
                if score:
                    audit = score.get("audit", 0)
                    cmds = score.get("commands_used", 0)
                    status_str += f" Best: Risk {audit}, Cmds {cmds}"
            else:
                is_unlocked = (idx == 0) or (self.levels[idx - 1]["id"] in self.cleared)
                if is_unlocked:
                    status_str = "[PLAY]"
                else:
                    status_str = "[LOCKED]"
            
            display_text = f"Level {idx + 1:02d}: {title:<25} {status_str}"
            item = ListItem(Static(display_text, markup=False), id=f"lvl-{idx}")
            list_view.append(item)
            
        if len(self.levels) > 0:
            list_view.index = 0
            self._update_details(0)
            list_view.focus()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item and event.item.id:
            try:
                idx = int(event.item.id.split("-")[1])
                self._update_details(idx)
            except (ValueError, IndexError):
                pass

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item and event.item.id:
            try:
                idx = int(event.item.id.split("-")[1])
                self.launch_level(idx)
            except (ValueError, IndexError):
                pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "launch":
            list_view = self.query_one("#level-list", ListView)
            if list_view.index is not None:
                self.launch_level(list_view.index)
        elif event.button.id == "back":
            self.action_back()

    def action_back(self) -> None:
        self.app.switch_screen("menu")

    def _update_details(self, idx: int) -> None:
        if idx < 0 or idx >= len(self.levels):
            return
        
        lvl = self.levels[idx]
        title = lvl["title"]
        briefing = lvl["briefing"]
        period = lvl["current_period"]
        cmd_limit = lvl["command_limit"]
        audit_limit = lvl["audit_limit"]
        rules = lvl["rules"]
        
        lvl_id = lvl["id"]
        status_str = ""
        if lvl_id in self.cleared:
            status_str = "[CLEAR] Passed the audit."
            best_scores = self.save_data.get("best_scores", {})
            score = best_scores.get(lvl_id)
            if score:
                audit = score.get("audit", 0)
                cmds = score.get("commands_used", 0)
                status_str += f"\nBest Score: Risk {audit}, Commands Used {cmds}"
        else:
            is_unlocked = (idx == 0) or (self.levels[idx - 1]["id"] in self.cleared)
            if is_unlocked:
                status_str = "[PLAY] Unlocked and ready."
            else:
                status_str = "[LOCKED] Pass previous levels to unlock."
                
        rules_text = "\n".join(f"- {rule}" for rule in rules)
        
        details_text = (
            f"[bold green]MISSION DETAILS[/]\n\n"
            f"[bold]Level {idx + 1:02d}:[/] {title}\n"
            f"[bold]Status:[/] {status_str}\n\n"
            f"[bold]Target Period:[/] {period}\n"
            f"[bold]Command Limit:[/] {cmd_limit} actions\n"
            f"[bold]Audit Risk Limit:[/] {audit_limit} risk points\n\n"
            f"[bold green]MISSION BRIEFING[/]\n"
            f"{briefing}\n\n"
            f"[bold green]LEVEL RULES[/]\n"
            f"{rules_text}"
        )
        
        details_text = details_text.replace("[bold]", "[b]").replace("[/bold]", "[/b]").replace("[bold green]", "[b green]").replace("[/bold green]", "[/b green]")
        
        details_panel = self.query_one("#level-details", Static)
        details_panel.update(details_text)

    def launch_level(self, idx: int) -> None:
        # Check lock
        if idx > 0:
            prev_lvl_id = self.levels[idx - 1]["id"]
            if prev_lvl_id not in self.cleared:
                return
        
        # Load the level in GameScreen
        game_screen = self.app.get_screen("game")
        game_screen.engine.current_level_index = idx
        # Save last_level progress
        game_screen.engine.save_data["last_level"] = idx
        save_game(game_screen.engine.save_data, game_screen.engine._save_path)
        
        # Load the level
        game_screen.engine._load_current_level()
        game_screen.log_lines = []
        game_screen._log(f"System online. Loaded level {idx + 1}: {game_screen.engine.level['title']}.")
        if game_screen.is_mounted:
            game_screen._refresh()
        
        # Switch to game
        self.app.switch_screen("game")