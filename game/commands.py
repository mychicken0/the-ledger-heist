from __future__ import annotations

import re

from game.engine import CommandResult, GameEngine, GameView
from game.documents import DocumentError
from game.ledger import LedgerError



class CommandProcessor:
    def __init__(self, engine: GameEngine) -> None:
        self.engine = engine

    def execute(self, raw_command: str) -> CommandResult:
        raw_command = raw_command.strip()
        if not raw_command:
            return CommandResult("Enter a command. Try 'help'.")

        parts = raw_command.split()
        command = parts[0].lower()

        if command == "help":
            return CommandResult(self._help())
        if command == "scan":
            return CommandResult(self._scan(self.engine.get_view()))
        if command in {"accounts", "list"}:
            return CommandResult(self._accounts(self.engine.get_view()))
        if command == "rules":
            return CommandResult(self._rules(self.engine.get_view()))
        if command == "entry":
            return self._entry(parts)

        if command == "ledger":
            return self._ledger(parts)
        if command == "trial":
            return CommandResult(self._trial(self.engine.get_view()))
        if command == "docs":
            if len(parts) != 1:
                return CommandResult("Usage: docs")
            return CommandResult(self._docs(self.engine.get_view()))
        if command in {"ls", "dir"}:
            path = parts[1] if len(parts) > 1 else ""
            return self._vfs_ls(path)
        if command == "cd":
            path = parts[1] if len(parts) > 1 else "/"
            return self._vfs_cd(path)
        if command in {"cat", "read", "view"}:
            path = parts[1] if len(parts) > 1 else ""
            return self._vfs_cat(path)
        if command == "tree":
            return self._vfs_tree()
        if command == "inspect":
            return self._inspect(parts)
        if command == "attach":
            return self._attach(parts)
        if command in {"adjust", "siphon"}:
            return CommandResult(
                f"'{command}' has been retired. Use journal entries, for example: "
                "entry debit cash 100 credit service_revenue 100 memo"
            )
        if command == "lock":
            if len(parts) != 1:
                return CommandResult("Usage: lock")
            return self.engine.lock()
        if command == "undo":
            if len(parts) != 1:
                return CommandResult("Usage: undo")
            return self.engine.undo()
        if command == "restart":
            if len(parts) != 1:
                return CommandResult("Usage: restart")
            return self.engine.restart()
        if command == "exit":
            if len(parts) != 1:
                return CommandResult("Usage: exit")
            return CommandResult("Exiting The Ledger Heist.", should_exit=True)

        return CommandResult(f"Unknown command '{parts[0]}'. Try 'help'.")

    def _entry(self, parts: list[str]) -> CommandResult:
        if len(parts) < 7:
            return CommandResult(
                "Usage: entry debit <account> <amount> credit <account> <amount> [memo text]"
            )

        debit_lines: list[tuple[str, int]] = []
        credit_lines: list[tuple[str, int]] = []
        index = 1
        while index < len(parts) and parts[index].lower() in {"debit", "credit"}:
            if index + 2 >= len(parts):
                return CommandResult(
                    "Usage: entry debit <account> <amount> credit <account> <amount> [memo text]"
                )
            side = parts[index].lower()
            account = parts[index + 1]
            amount = self._parse_positive_int(parts[index + 2], "Entry amount")
            if isinstance(amount, CommandResult):
                return amount
            if side == "debit":
                debit_lines.append((account, amount))
            else:
                credit_lines.append((account, amount))
            index += 3

        memo = " ".join(parts[index:]) or "No memo"
        return self.engine.post_entry(debit_lines, credit_lines, memo)



    def _ledger(self, parts: list[str]) -> CommandResult:
        if len(parts) != 2:
            return CommandResult("Usage: ledger <account>")
        account = parts[1]
        try:
            lines = self.engine.account_ledger_lines(account)
            resolved = self.engine.ledger.get_account(account).name
        except LedgerError as error:
            return CommandResult(str(error))

        if not lines:
            return CommandResult(f"Ledger for {resolved}: no activity yet.")
        output = [
            f"Ledger for {resolved}:",
            f"{'Entry':<10} {'Period':<9} {'Debit':>8} {'Credit':>8} {'Run Bal':>9} Memo",
        ]
        for line in lines:
            output.append(
                f"{line.entry_id:<10} {line.period:<9} {line.debit_amount:>8} "
                f"{line.credit_amount:>8} {line.running_balance:>9} {line.memo}"
            )
        return CommandResult("\n".join(output))

    def _parse_positive_int(self, value: str, label: str) -> int | CommandResult:
        try:
            amount = int(value)
        except ValueError:
            return CommandResult(f"{label} must be an integer.")
        if amount <= 0:
            return CommandResult(f"{label} must be a positive integer.")
        return amount

    def _help(self) -> str:
        return (
            "Commands:\n"
            "  help\n"
            "  scan\n"
            "  accounts                   (list is an alias)\n"
            "  rules\n"
            "  entry debit <account> <amount> credit <account> <amount> [memo text]\n"
            "  ledger <account>\n"
            "  trial\n"
            "  docs\n"
            "  ls [path] / dir [path]     - List directory contents\n"
            "  cd <path>                  - Change directory\n"
            "  cat <file> / read <file>   - Read file or inspect document\n"
            "  tree                       - Print directory tree\n"
            "  inspect <document_id>      - Inspect supporting document\n"
            "  attach <document_id> <JE>  - Attach document to journal entry\n"
            "  lock\n"
            "  undo\n"
            "  restart\n"
            "  exit"
        )

    def _inspect(self, parts: list[str]) -> CommandResult:
        if len(parts) != 2:
            return CommandResult("Usage: inspect <document_id>")
        return self._vfs_cat(parts[1])

    def _vfs_ls(self, path: str) -> CommandResult:
        res = self.engine.vfs.ls(path)
        if isinstance(res, str):
            return CommandResult(res)

        lines = []
        for node in res:
            if node.is_directory:
                lines.append(f"📁 {node.name}/")
            else:
                icon = "💼" if node.name.endswith(".doc") else "📄"
                lines.append(f"{icon} {node.name}")
        if not lines:
            return CommandResult("(directory is empty)")
        return CommandResult("\n".join(lines))

    def _vfs_cd(self, path: str) -> CommandResult:
        res = self.engine.vfs.cd(path)
        if isinstance(res, str):
            return CommandResult(res)
        prompt_path = self.engine.vfs.get_path_string()
        return CommandResult(f"Changed directory to {prompt_path}", state_changed=True)

    def _vfs_cat(self, path: str) -> CommandResult:
        node = self.engine.vfs.resolve_path(path)
        if not node:
            # Fallback global search for document ID or name
            clean_name = path.lower()
            if not clean_name.endswith(".doc"):
                clean_name += ".doc"

            found_node = None
            for key, val in self.engine.vfs.root.children.items():
                if val.is_directory and val.children:
                    for fkey, fval in val.children.items():
                        if fkey == clean_name or fkey.split(".")[0] == path.lower():
                            found_node = fval
                            break
                if found_node:
                    break

            if found_node:
                node = found_node
            else:
                return CommandResult(f"File or document '{path}' not found.")

        if node.is_directory:
            return CommandResult(f"'{path}' is a directory.")

        if node.document:
            # Set active file and document ID in the engine
            self.engine.active_file = (node.name, "", node.document)
            self.engine.active_document_id = node.document.document_id

            related = node.document.related_account or "none"
            desc = node.document.description
            return CommandResult(
                f"Document inspection for '{node.name}':\n"
                f"  id:              {node.document.document_id}\n"
                f"  type:            {node.document.document_type}\n"
                f"  amount:          {node.document.amount}\n"
                f"  related account: {related}\n"
                f"  period:          {node.document.period}\n"
                f"  description:     {desc}",
                state_changed=True,
            )
        else:
            # Text file
            self.engine.active_file = (node.name, node.content or "", None)
            return CommandResult(
                f"--- File: {node.name} ---\n{node.content}",
                state_changed=True,
            )

    def _vfs_tree(self) -> CommandResult:
        lines = ["Virtual File System Tree:"]

        def render_node(node, indent=""):
            if not node.children:
                return
            sorted_keys = sorted(
                node.children.keys(),
                key=lambda k: (not node.children[k].is_directory, k)
            )
            for i, key in enumerate(sorted_keys):
                child = node.children[key]
                is_last = (i == len(sorted_keys) - 1)
                branch = "└── " if is_last else "├── "
                next_indent = indent + ("    " if is_last else "│   ")

                if child.is_directory:
                    lines.append(f"{indent}{branch}📁 {child.name}/")
                    render_node(child, next_indent)
                else:
                    icon = "💼" if child.name.endswith(".doc") else "📄"
                    lines.append(f"{indent}{branch}{icon} {child.name}")

        render_node(self.engine.vfs.root)
        return CommandResult("\n".join(lines))

    def _attach(self, parts: list[str]) -> CommandResult:
        if len(parts) != 3:
            return CommandResult("Usage: attach <document_id> <entry_id>")
        return self.engine.attach_document(parts[1], parts[2])

    def _scan(self, view: GameView) -> str:
        trial_state = "BALANCED" if view.is_trial_balanced else "IMBALANCED"
        objectives_open = sum(1 for objective in view.objectives if not objective.passed)
        flags = ", ".join(view.active_flags) if view.active_flags else "none"
        attached = len(view.attached_documents)
        return (
            "Accounting scan:\n"
            f"  Trial balance: {trial_state} ({view.total_debits}/{view.total_credits})\n"
            f"  Period:        {view.current_period} ({view.period_status})\n"
            f"  Audit risk:    {view.audit_risk}/{view.audit_limit}\n"
            f"  Commands:      {view.commands_left}/{view.command_limit}\n"
            f"  Documents:     {attached}/{len(view.documents)} attached\n"
            f"  Objectives:    {len(view.objectives) - objectives_open}/{len(view.objectives)} complete\n"
            f"  Audit flags:   {flags}"
        )

    def _accounts(self, view: GameView) -> str:
        lines = [
            "Accounts:",
            f"{'Account':<22} {'Type':<10} {'Normal':<7} {'Balance':>8} {'Locked':<6} Notes",
        ]
        for account in view.accounts:
            locked = "yes" if account.locked else "no"
            lines.append(
                f"{account.name:<22} {account.display_type:<10} {account.normal_side:<7} "
                f"{account.balance:>8} {locked:<6} {account.notes}"
            )
        return "\n".join(lines)

    def _rules(self, view: GameView) -> str:
        lines = [f"Level {view.level_number}: {view.title}", "Rules:"]
        lines.extend(f"- {rule}" for rule in view.rules)
        lines.append("Objectives:")
        lines.extend(
            f"- [{'x' if objective.passed else ' '}] {objective.name}: {objective.detail}"
            for objective in view.objectives
        )
        return "\n".join(lines)

    def _trial(self, view: GameView) -> str:
        lines = [
            "Trial balance:",
            f"{'Account':<22} {'Debit':>9} {'Credit':>9} {'Type':<10} Status",
        ]
        for row in view.trial_rows:
            lines.append(
                f"{row.account:<22} {row.debit_balance:>9} {row.credit_balance:>9} "
                f"{row.account_type:<10} {row.status}"
            )
        status = "balanced" if view.is_trial_balanced else "imbalanced"
        lines.append("-" * 62)
        lines.append(f"{'TOTAL':<22} {view.total_debits:>9} {view.total_credits:>9} {status}")
        return "\n".join(lines)

    def _docs(self, view: GameView) -> str:
        if not view.documents:
            return "Documents: no supporting documents for this level."
        attached = {document_id for document_id in view.attached_documents.values()}
        lines = [
            "Documents:",
            f"{'ID':<12} {'Type':<14} {'Amount':>8} {'Period':<9} {'Status':<9} Description",
        ]
        for document in view.documents:
            status = "attached" if document.document_id in attached else "open"
            lines.append(
                f"{document.document_id:<12} {document.document_type:<14} {document.amount:>8} "
                f"{document.period:<9} {status:<9} {document.description}"
            )
        return "\n".join(lines)
