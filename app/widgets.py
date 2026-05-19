from __future__ import annotations

from textual.widgets import Log, Static, Tree
from rich.table import Table
from rich.console import Group
from rich.text import Text
from rich import box
from rich.columns import Columns
from rich.panel import Panel
from rich.align import Align

from game.engine import GameView
from game.documents import SupportingDocument
from game.vfs import VirtualFileSystem


class AccountingPanel(Static):
    def __init__(self, **kwargs) -> None:
        super().__init__("", markup=False, **kwargs)
        self.border_title = "ACCOUNTS / TRIAL"

    def update_view(self, view: GameView) -> None:
        table = Table(
            title_justify="left",
            box=box.SQUARE,
            expand=True,
            title_style="bold #7dffae",
            border_style="#1d7a4a",
            header_style="bold #a8ffc9"
        )
        table.add_column("Account", justify="left", ratio=3)
        table.add_column("Type", justify="left", ratio=2)
        table.add_column("Bal", justify="right", ratio=2)
        table.add_column("N", justify="center")
        table.add_column("L", justify="center")

        for account in view.accounts:
            locked = "Y" if account.locked else "N"
            table.add_row(
                account.name,
                account.display_type,
                str(account.balance),
                account.normal_side[:1].upper(),
                locked
            )

        status = "BALANCED" if view.is_trial_balanced else "IMBALANCED"
        status_color = "bold #5bdd91" if view.is_trial_balanced else "bold red"
        summary = Text.assemble(
            ("\nDebits  ", ""), (str(view.total_debits), "bold"),
            ("\nCredits ", ""), (str(view.total_credits), "bold"),
            ("\nStatus  ", ""), (status, status_color)
        )
        
        self.update(Group(table, summary))



class JournalEntriesPanel(Static):
    def __init__(self, **kwargs) -> None:
        super().__init__("", markup=False, **kwargs)
        self.border_title = "JOURNAL ENTRIES"

    def update_view(self, view: GameView) -> None:
        lines = []
        if not view.journal_entries:
            lines.append("No entries posted.")
        for entry in view.journal_entries[-8:]:
            debit_text = ", ".join(f"{line.account}:{line.amount}" for line in entry.debit_lines)
            credit_text = ", ".join(f"{line.account}:{line.amount}" for line in entry.credit_lines)
            document = entry.document_id or "no-doc"
            lines.append(f"{entry.entry_id} {entry.period}")
            lines.append(f"  D {debit_text}")
            lines.append(f"  C {credit_text}")
            lines.append(f"  Doc {document} | {entry.memo}")
        self.update("\n".join(lines))


class StatusPanel(Static):
    can_focus = True

    def __init__(self, **kwargs) -> None:
        super().__init__("", markup=False, **kwargs)
        self.border_title = "STATUS / OBJECTIVES"

    def update_view(self, view: GameView) -> None:
        trial = "OK" if view.is_trial_balanced else "OPEN"
        lines = [
            f"Level     {view.level_number}/{view.total_levels}",
            f"Period    {view.current_period} {view.period_status}",
            f"Audit     {view.audit_risk}/{view.audit_limit}",
            f"Commands  {view.commands_left}/{view.command_limit}",
            f"Trial     {trial}",
            f"Docs      {len(view.attached_documents)}/{len(view.documents)}",
            "",
            "Objectives:",
        ]
        for objective in view.objectives:
            marker = "x" if objective.passed else " "
            lines.append(f"[{marker}] {objective.name}: {objective.detail}")
        if view.active_flags:
            lines.extend(["", "Flags:"])
            lines.extend(f"- {flag}" for flag in view.active_flags[-4:])
        self.update("\n".join(lines))


class AuditLogPanel(Log):
    def __init__(self, **kwargs) -> None:
        super().__init__(highlight=False, auto_scroll=True, **kwargs)
        self.border_title = "AUDIT LOG"

    def update_log(self, lines: list[str]) -> None:
        if not lines:
            content_lines = ["Awaiting command stream."]
        else:
            content_lines = [*lines]
        self.clear()
        self.write_lines(content_lines)
        self.scroll_end(animate=False)


class MissionBriefingPanel(Static):
    def __init__(self, **kwargs) -> None:
        super().__init__("", markup=False, **kwargs)
        self.border_title = "MISSION BRIEFING"

    def update_view(self, view: GameView) -> None:
        text = Text()
        text.append(f"LEVEL {view.level_number}/{view.total_levels}: {view.title}\n", style="bold #a8ffc9")
        text.append(f"Period: {view.current_period} ({view.period_status}) | Commands: {view.commands_left}/{view.command_limit}\n\n", style="italic #5bdd91")
        text.append(view.briefing, style="#d9ffe8")
        self.update(text)


class DocumentViewerPanel(Static):
    def __init__(self, **kwargs) -> None:
        super().__init__("", markup=True, **kwargs)
        self.border_title = "DOCUMENT VIEWER"

    def update_view(
        self,
        view: GameView,
        active_file: tuple[str, str, SupportingDocument | None] | None,
    ) -> None:
        if active_file:
            name, content, doc = active_file
            if doc:
                self.border_title = doc.document_type.upper()
                self.update(self._render_document(doc))
            else:
                self.border_title = f"FILE: {name.upper()}"
                self.update(Text(content, style="#a8ffc9"))
        else:
            self.border_title = "DOCUMENT VIEWER"
            welcome_text = Text()
            welcome_text.append("NO ACTIVE DOCUMENT LOADED\n\n", style="bold #ff5d5d")
            welcome_text.append("Use terminal commands to navigate and view files:\n", style="#8dffb8")
            welcome_text.append("  > ls          - List directory\n", style="bold #5bdd91")
            welcome_text.append("  > cd <dir>    - Change directory\n", style="bold #5bdd91")
            welcome_text.append("  > cat <file>  - Read/Inspect file\n\n", style="bold #5bdd91")
            welcome_text.append("Alternatively, use the FILE SYSTEM tree.\nClick on any file node to inspect its contents.", style="#8dffb8")
            self.update(Align.center(welcome_text, vertical="middle"))

    def _render_document(self, doc: SupportingDocument) -> Group | Text:
        dtype = doc.document_type.upper()
        rel_acc = doc.related_account or "NONE"

        if doc.document_type == "invoice":
            table = Table(box=None, expand=True)
            table.add_column("Description", style="#a8ffc9", ratio=3)
            table.add_column("Amount", style="bold #7dffae", justify="right", ratio=1)
            table.add_row(doc.description or "Consulting & Services Rendered", f"${doc.amount:,.2f}")

            content = Group(
                Text.assemble(
                    ("INVOICE NO: ", "bold #8dffb8"), (f"{doc.document_id.upper()}\n", "bold #d6ffe4"),
                    ("PERIOD:     ", "#8dffb8"), (f"{doc.period}\n", "#d6ffe4"),
                    ("TO:         ", "#8dffb8"), ("The Ledger Corporation\n", "#d6ffe4"),
                    ("ACCOUNT:    ", "#8dffb8"), (f"{rel_acc.upper()}\n", "#d6ffe4"),
                    ("-" * 38 + "\n", "#155f3a")
                ),
                table,
                Text.assemble(
                    ("\n" + "-" * 38 + "\n", "#155f3a"),
                    ("TOTAL DUE:  ", "bold #7dffae"), (f"${doc.amount:,.2f}", "bold #7dffae")
                )
            )
            return content

        elif doc.document_type == "receipt":
            content = Text()
            content.append("\n  *** TRANSACTIONS RECEIPT ***\n\n", style="bold #7dffae")
            content.append(f"  RECEIPT ID: {doc.document_id.upper()}\n", style="bold #8dffb8")
            content.append(f"  DATE/PER:   {doc.period}\n", style="#8dffb8")
            content.append(f"  ACCOUNT:    {rel_acc.upper()}\n", style="#8dffb8")
            content.append("  " + "-" * 38 + "\n", style="#155f3a")
            content.append(f"  {doc.description or 'Sales payment received'}\n", style="#a8ffc9")
            content.append("  " + "-" * 38 + "\n", style="#155f3a")
            content.append(f"  PAID AMOUNT:  ${doc.amount:,.2f}\n", style="bold #7dffae")
            content.append("  STATUS:       PAID IN FULL\n", style="bold #5bdd91")
            return content

        elif doc.document_type == "timesheet":
            content = Text()
            content.append("\n  WORK HOURS SUMMARY\n\n", style="bold #7dffae")
            content.append(f"  TIMESHEET ID: {doc.document_id.upper()}\n", style="bold #8dffb8")
            content.append(f"  PERIOD:       {doc.period}\n", style="#8dffb8")
            content.append(f"  DEPARTMENT:   Operations\n", style="#8dffb8")
            content.append(f"  RELATED ACCT: {rel_acc.upper()}\n", style="#8dffb8")
            content.append("  " + "-" * 38 + "\n", style="#155f3a")
            content.append(f"  Activity: {doc.description}\n", style="#a8ffc9")
            content.append(f"  Approved Hours: 40.0 hours\n", style="#a8ffc9")
            content.append("  " + "-" * 38 + "\n", style="#155f3a")
            content.append(f"  CALCULATED WAGES: ${doc.amount:,.2f}\n", style="bold #7dffae")
            return content

        elif doc.document_type == "contract":
            content = Text()
            content.append("\n  MUTUAL LEGAL AGREEMENT\n\n", style="bold #7dffae")
            content.append(f"  CONTRACT REF: {doc.document_id.upper()}\n", style="bold #8dffb8")
            content.append(f"  PERIOD:       {doc.period}\n", style="#8dffb8")
            content.append(f"  TERMS:        Net 30\n", style="#8dffb8")
            content.append("  " + "-" * 38 + "\n", style="#155f3a")
            content.append(f"  Whereas, the parties agree to deliver services:\n", style="#a8ffc9")
            content.append(f"  '{doc.description}'\n\n", style="italic #d6ffe4")
            content.append(f"  CONTRACT VALUE: ${doc.amount:,.2f}\n", style="bold #7dffae")
            content.append("  SIGNATURE:    APPROVED & SIGNED\n", style="#5bdd91")
            return content

        elif doc.document_type == "schedule":
            content = Text()
            content.append("\n  DEPRECIATION SCHEDULE\n\n", style="bold #7dffae")
            content.append(f"  SCHEDULE ID:  {doc.document_id.upper()}\n", style="bold #8dffb8")
            content.append(f"  PERIOD:       {doc.period}\n", style="#8dffb8")
            content.append(f"  ASSET CLASS:  Equipment / Capitalized\n", style="#8dffb8")
            content.append("  " + "-" * 38 + "\n", style="#155f3a")
            content.append(f"  Depreciation Method: Straight-Line\n", style="#a8ffc9")
            content.append(f"  Asset Notes: {doc.description}\n", style="#a8ffc9")
            content.append("  " + "-" * 38 + "\n", style="#155f3a")
            content.append(f"  PERIOD DEPRECIATION: ${doc.amount:,.2f}\n", style="bold #7dffae")
            return content

        elif doc.document_type == "resolution":
            content = Text()
            content.append("\n  BOARD OF DIRECTORS RESOLUTION\n\n", style="bold #7dffae")
            content.append(f"  RESOLUTION REF: {doc.document_id.upper()}\n", style="bold #8dffb8")
            content.append(f"  MEETING DATE:   {doc.period}\n", style="#8dffb8")
            content.append("  " + "-" * 38 + "\n", style="#155f3a")
            content.append(f"  It is hereby resolved that the company shall:\n", style="#a8ffc9")
            content.append(f"  '{doc.description}'\n\n", style="italic #d6ffe4")
            content.append(f"  AUTHORIZED FUND: ${doc.amount:,.2f}\n", style="bold #7dffae")
            content.append("  ATTESTED BY:     SECRETARY OF THE BOARD\n", style="#5bdd91")
            return content

        content = Text()
        content.append(f"\n  OFFICIAL SUPPORTING DOCUMENT\n\n", style="bold #7dffae")
        content.append(f"  DOCUMENT ID: {doc.document_id.upper()}\n", style="bold #8dffb8")
        content.append(f"  TYPE:        {dtype}\n", style="#8dffb8")
        content.append(f"  PERIOD:      {doc.period}\n", style="#8dffb8")
        content.append(f"  ACCOUNT:     {rel_acc.upper()}\n", style="#8dffb8")
        content.append("  " + "-" * 38 + "\n", style="#155f3a")
        content.append(f"  Description: {doc.description}\n", style="#a8ffc9")
        content.append("  " + "-" * 38 + "\n", style="#155f3a")
        content.append(f"  RECORDED AMOUNT: ${doc.amount:,.2f}\n", style="bold #7dffae")
        return content


class FileSystemPanel(Tree):
    def __init__(self, **kwargs) -> None:
        super().__init__("Root (/) [click to inspect]", **kwargs)
        self.border_title = "FILE SYSTEM"

    def update_vfs(self, vfs: VirtualFileSystem) -> None:
        self.clear()

        def populate_node(tree_node, vfs_node):
            if vfs_node.children:
                sorted_keys = sorted(
                    vfs_node.children.keys(),
                    key=lambda k: (not vfs_node.children[k].is_directory, k),
                )
                for key in sorted_keys:
                    child = vfs_node.children[key]
                    if child.is_directory:
                        dir_label = f"[DIR] {child.name}"
                        sub_tree = tree_node.add(dir_label, expand=True)
                        populate_node(sub_tree, child)
                    else:
                        icon = "[DOC]" if child.name.endswith(".doc") else "[TXT]"
                        file_label = f"{icon} {child.name}"
                        tree_node.add_leaf(file_label)

        populate_node(self.root, vfs.root)
