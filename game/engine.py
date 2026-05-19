from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from game.documents import DocumentError, SupportingDocument
from game.ledger import Account, JournalEntry, Ledger, LedgerError, TrialBalanceRow
from game.level_loader import load_levels
from game.save_system import load_save, save_game
from game.vfs import VirtualFileSystem


@dataclass(frozen=True)
class CommandResult:
    message: str
    state_changed: bool = False
    won: bool = False
    should_exit: bool = False


@dataclass(frozen=True)
class ObjectiveStatus:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class GameSnapshot:
    ledger: Ledger
    audit_risk: int
    commands_left: int
    entry_counter: int
    active_flags: list[str]
    resolved_flags: list[str]
    attached_documents: dict[str, str]
    off_normal_post_count: int
    round_entry_count: int


@dataclass(frozen=True)
class GameView:
    level_number: int
    total_levels: int
    level_id: str
    title: str
    briefing: str
    current_period: str
    period_status: str
    accounts: tuple[Account, ...]
    journal_entries: tuple[JournalEntry, ...]
    documents: tuple[SupportingDocument, ...]
    attached_documents: dict[str, str]
    trial_rows: tuple[TrialBalanceRow, ...]
    total_debits: int
    total_credits: int
    is_trial_balanced: bool
    audit_risk: int
    audit_limit: int
    commands_left: int
    command_limit: int
    rules: tuple[str, ...]
    objectives: tuple[ObjectiveStatus, ...]
    active_flags: tuple[str, ...]
    resolved_flags: tuple[str, ...]


class GameEngine:
    def __init__(
        self,
        levels: list[dict[str, Any]] | None = None,
        save_path: Path | None = None,
    ) -> None:
        self.levels = levels or load_levels()
        self._save_path = save_path
        self.save_data = load_save(save_path)
        self.current_level_index = self._clamped_level_index(self.save_data.get("last_level", 0))
        self._load_current_level()

    @property
    def level(self) -> dict[str, Any]:
        return self.levels[self.current_level_index]

    @property
    def command_limit(self) -> int:
        return int(self.level["command_limit"])

    @property
    def audit_limit(self) -> int:
        return int(self.level["audit_limit"])

    @property
    def objectives(self) -> dict[str, Any]:
        return dict(self.level.get("objectives", {}))

    def get_view(self) -> GameView:
        return GameView(
            level_number=self.current_level_index + 1,
            total_levels=len(self.levels),
            level_id=str(self.level["id"]),
            title=str(self.level["title"]),
            briefing=str(self.level["briefing"]),
            current_period=self.current_period,
            period_status="open" if self._period_is_open() else "closed",
            accounts=tuple(account.clone() for account in self.ledger.accounts.values()),
            journal_entries=tuple(self.ledger.journal_entries),
            documents=tuple(self.documents.values()),
            attached_documents=dict(self.attached_documents),
            trial_rows=tuple(self.ledger.trial_balance()),
            total_debits=self.ledger.total_debits,
            total_credits=self.ledger.total_credits,
            is_trial_balanced=self.ledger.is_trial_balanced,
            audit_risk=self.audit_risk,
            audit_limit=self.audit_limit,
            commands_left=self.commands_left,
            command_limit=self.command_limit,
            rules=tuple(self.level["rules"]),
            objectives=tuple(self.objective_statuses()),
            active_flags=tuple(self.active_flags),
            resolved_flags=tuple(self.resolved_flags),
        )

    def post_entry(
        self,
        debit_lines: list[tuple[str, int]],
        credit_lines: list[tuple[str, int]],
        memo: str,
    ) -> CommandResult:
        if not self._period_is_open():
            self._add_risk(3, f"Attempted posting to closed period {self.current_period}.")
            return CommandResult(
                f"Period {self.current_period} is closed. Restart or use a later phase reversal flow.",
                state_changed=True,
            )
        if not self._can_spend_command():
            return CommandResult("No commands left. Undo, restart, or lock if objectives pass.")

        entry_id = f"JE-{self.entry_counter:04d}"
        self._push_snapshot()
        try:
            entry = self.ledger.post_entry(
                entry_id=entry_id,
                period=self.current_period,
                debit_lines=debit_lines,
                credit_lines=credit_lines,
                memo=memo,
            )
        except LedgerError as error:
            self._undo_stack.pop()
            self._audit_rejected_entry(str(error))
            return CommandResult(str(error), state_changed=True)

        self.entry_counter += 1
        self.commands_left -= 1
        self._audit_posted_entry(entry)
        self.update_vfs_dynamic_files()
        return CommandResult(self._entry_posted_message(entry), state_changed=True)

    def attach_document(self, document_id: str, entry_id: str) -> CommandResult:
        if not self._period_is_open():
            self._add_risk(2, f"Attempted document attachment in closed period {self.current_period}.")
            return CommandResult(f"Period {self.current_period} is closed.", state_changed=True)

        document_key = document_id.lower()
        if document_key not in self.documents:
            return CommandResult(f"Document '{document_id}' does not exist.")

        self._push_snapshot()
        try:
            entry = self.ledger.attach_document(entry_id, document_key)
        except LedgerError as error:
            self._undo_stack.pop()
            return CommandResult(str(error))

        self.attached_documents[entry.entry_id] = document_key
        warnings = self._audit_document_attachment(self.documents[document_key], entry)
        suffix = "" if not warnings else " " + " ".join(warnings)
        self.update_vfs_dynamic_files()
        return CommandResult(
            f"Attached {document_key} to {entry.entry_id}.{suffix}",
            state_changed=True,
        )

    def get_document(self, document_id: str) -> SupportingDocument:
        document_key = document_id.lower()
        if document_key not in self.documents:
            raise DocumentError(f"Document '{document_id}' does not exist.")
        return self.documents[document_key]

    def undo(self) -> CommandResult:
        if not self._period_is_open():
            return CommandResult("Undo is locked after a period closes. Restart the level to reset.")
        if not self._undo_stack:
            return CommandResult("Nothing to undo.")
        snapshot = self._undo_stack.pop()
        self.ledger = snapshot.ledger.clone()
        self.audit_risk = snapshot.audit_risk
        self.commands_left = snapshot.commands_left
        self.entry_counter = snapshot.entry_counter
        self.active_flags = list(snapshot.active_flags)
        self.resolved_flags = list(snapshot.resolved_flags)
        self.attached_documents = dict(snapshot.attached_documents)
        self._off_normal_post_count = snapshot.off_normal_post_count
        self._round_entry_count = snapshot.round_entry_count
        self.update_vfs_dynamic_files()
        return CommandResult("Last journal entry undone.", state_changed=True)

    def restart(self) -> CommandResult:
        self._load_current_level()
        return CommandResult("Level restarted from the opening ledger.", state_changed=True)

    def lock(self) -> CommandResult:
        failures = self._lock_failures()
        if failures:
            self._add_risk(2, "Failed lock attempt: objectives still open.")
            return CommandResult("Lock rejected:\n" + "\n".join(f"- {failure}" for failure in failures), state_changed=True)

        current_id = str(self.level["id"])
        current_title = str(self.level["title"])
        self._record_clear(current_id)

        if self.current_level_index + 1 < len(self.levels):
            self.current_level_index += 1
            self.save_data["last_level"] = self.current_level_index
            save_game(self.save_data, self._save_path)
            next_title = str(self.levels[self.current_level_index]["title"])
            self._load_current_level()
            return CommandResult(
                f"LOCK ACCEPTED. {current_title} cleared. Advancing to {next_title}.",
                state_changed=True,
                won=True,
            )

        self.save_data["last_level"] = self.current_level_index
        save_game(self.save_data, self._save_path)
        return CommandResult(
            f"LOCK ACCEPTED. {current_title} cleared. Tutorial track complete.",
            state_changed=True,
            won=True,
        )

    def account_ledger_lines(self, account: str):
        return self.ledger.account_ledger(account)

    def objective_statuses(self) -> list[ObjectiveStatus]:
        statuses: list[ObjectiveStatus] = []
        objectives = self.objectives

        if objectives.get("trial_balance_balanced"):
            statuses.append(
                ObjectiveStatus(
                    "Trial balance",
                    self.ledger.is_trial_balanced,
                    "debits equal credits"
                    if self.ledger.is_trial_balanced
                    else f"debits {self.ledger.total_debits}, credits {self.ledger.total_credits}",
                )
            )

        max_audit = objectives.get("max_audit_risk")
        if isinstance(max_audit, int):
            statuses.append(
                ObjectiveStatus(
                    "Audit risk",
                    self.audit_risk <= max_audit,
                    f"{self.audit_risk}/{max_audit}",
                )
            )

        min_entries = objectives.get("min_entries")
        if isinstance(min_entries, int):
            count = len(self.ledger.journal_entries)
            statuses.append(
                ObjectiveStatus(
                    "Journal entries",
                    count >= min_entries,
                    f"{count}/{min_entries} posted",
                )
            )

        required_balances = objectives.get("required_balances", {})
        if isinstance(required_balances, dict):
            for account_name, expected in required_balances.items():
                try:
                    account = self.ledger.get_account(str(account_name))
                    actual = account.balance
                    passed = actual == int(expected)
                except (LedgerError, ValueError):
                    actual = "missing"
                    passed = False
                statuses.append(
                    ObjectiveStatus(
                        f"{account_name} balance",
                        passed,
                        f"{actual}/{expected}",
                    )
                )

        if objectives.get("no_suspense_remaining"):
            suspense_accounts = [
                account for account in self.ledger.accounts.values() if "suspense" in account.name
            ]
            passed = all(account.balance == 0 for account in suspense_accounts)
            statuses.append(
                ObjectiveStatus(
                    "Suspense cleared",
                    passed,
                    "zero balance" if passed else "suspense still has a balance",
                )
            )

        required_documents = objectives.get("required_documents_attached", [])
        if isinstance(required_documents, list):
            attached = {document_id.lower() for document_id in self.attached_documents.values()}
            for document_id in required_documents:
                document_key = str(document_id).lower()
                statuses.append(
                    ObjectiveStatus(
                        "Required document attached",
                        document_key in attached,
                        "attached" if document_key in attached else "not attached",
                    )
                )

        if objectives.get("all_entries_documented"):
            undocumented = [
                entry.entry_id for entry in self.ledger.journal_entries if not entry.document_id
            ]
            statuses.append(
                ObjectiveStatus(
                    "Entries documented",
                    not undocumented,
                    "all entries have support" if not undocumented else ", ".join(undocumented),
                )
            )

        required_accounts = objectives.get("required_accounts", [])
        if isinstance(required_accounts, list):
            for account_name in required_accounts:
                exists = str(account_name).lower() in self.ledger.accounts
                statuses.append(
                    ObjectiveStatus(
                        f"{account_name} account",
                        exists,
                        "present" if exists else "missing",
                    )
                )

        forbidden_accounts = objectives.get("forbidden_accounts", [])
        if isinstance(forbidden_accounts, list):
            for account_name in forbidden_accounts:
                account = self.ledger.accounts.get(str(account_name).lower())
                passed = account is None or account.balance == 0
                statuses.append(
                    ObjectiveStatus(
                        f"{account_name} forbidden",
                        passed,
                        "not used" if passed else "has balance",
                    )
                )
        return statuses

    def _get_objectives_text(self) -> str:
        lines = []
        for obj in self.objective_statuses():
            status = "[x]" if obj.passed else "[ ]"
            lines.append(f"{status} {obj.name}: {obj.detail}")
        return "\n".join(lines)

    def update_vfs_dynamic_files(self) -> None:
        if hasattr(self, "vfs") and self.vfs:
            obj_node = self.vfs.root.children.get("objectives.txt")
            if obj_node:
                obj_node.content = self._get_objectives_text()

    def _load_current_level(self) -> None:
        self.ledger = Ledger.from_level(self.level)
        self.current_period = str(self.level["current_period"])
        self.open_periods = {str(period) for period in self.level.get("open_periods", [])}
        self.closed_periods = {str(period) for period in self.level.get("closed_periods", [])}
        self.audit_risk = 0
        self.commands_left = self.command_limit
        self.entry_counter = 1
        self.active_flags: list[str] = []
        self.resolved_flags: list[str] = []
        self.documents = self._load_documents()
        self.attached_documents: dict[str, str] = {}
        self._off_normal_post_count = 0
        self._round_entry_count = 0
        self._undo_stack: list[GameSnapshot] = []
        self._load_opening_entries()

        # Initialize Virtual File System (VFS)
        obj_text = self._get_objectives_text()
        self.vfs = VirtualFileSystem(
            briefing=str(self.level["briefing"]),
            rules=list(self.level["rules"]),
            objectives_text=obj_text,
            documents=list(self.documents.values()),
        )
        self.active_file = None  # tuple of (name, content_str, doc_obj) or None
        self.active_document_id = None
        self.update_vfs_dynamic_files()

    def _load_opening_entries(self) -> None:
        for index, payload in enumerate(self.level.get("opening_entries", []), start=1):
            if not isinstance(payload, dict):
                continue
            debit_lines = self._payload_lines(payload.get("debit", []))
            credit_lines = self._payload_lines(payload.get("credit", []))
            try:
                self.ledger.post_entry(
                    entry_id=f"OPEN-{index:04d}",
                    period=str(payload.get("period", self.current_period)),
                    debit_lines=debit_lines,
                    credit_lines=credit_lines,
                    memo=str(payload.get("memo", "Opening entry")),
                    allow_locked=True,
                )
            except LedgerError:
                continue

    def _payload_lines(self, payload: Any) -> list[tuple[str, int]]:
        if not isinstance(payload, list):
            return []
        lines: list[tuple[str, int]] = []
        for line in payload:
            if isinstance(line, dict) and "account" in line and "amount" in line:
                lines.append((str(line["account"]), int(line["amount"])))
        return lines

    def _push_snapshot(self) -> None:
        self._undo_stack.append(
            GameSnapshot(
                ledger=self.ledger.clone(),
                audit_risk=self.audit_risk,
                commands_left=self.commands_left,
                entry_counter=self.entry_counter,
                active_flags=list(self.active_flags),
                resolved_flags=list(self.resolved_flags),
                attached_documents=dict(self.attached_documents),
                off_normal_post_count=self._off_normal_post_count,
                round_entry_count=self._round_entry_count,
            )
        )

    def _load_documents(self) -> dict[str, SupportingDocument]:
        documents: dict[str, SupportingDocument] = {}
        for payload in self.level.get("documents", []):
            if not isinstance(payload, dict):
                continue
            try:
                document = SupportingDocument.from_level(payload)
            except (DocumentError, KeyError, TypeError, ValueError):
                continue
            documents[document.document_id] = document
        return documents

    def _can_spend_command(self) -> bool:
        return self.commands_left > 0

    def _period_is_open(self) -> bool:
        return self.current_period in self.open_periods and self.current_period not in self.closed_periods

    def _audit_rejected_entry(self, message: str) -> None:
        lowered = message.lower()
        if "unbalanced" in lowered:
            self._add_risk(2, "Rejected unbalanced journal entry.")
        elif "locked" in lowered:
            self._add_risk(3, "Attempted to modify a locked account.")
        else:
            self._add_risk(1, "Rejected journal entry.")

    def _audit_posted_entry(self, entry: JournalEntry) -> None:
        opposite_lines = [
            line for line in entry.all_lines if line.side != self.ledger.accounts[line.account].normal_side
        ]
        self._off_normal_post_count += len(opposite_lines)
        if self._off_normal_post_count >= 3:
            self._add_risk(1, "Frequent entries against normal account sides.")

        if entry.total_debit >= 100 and entry.total_debit % 100 == 0:
            self._round_entry_count += 1
            if self._round_entry_count >= 3:
                self._add_risk(1, "Several round-number journal entries.")

        memo = entry.memo.lower()
        if any(word in memo for word in ("manual", "adjust", "plug")):
            self._add_risk(2, "Manual adjustment memo needs review.")

        suspense_accounts = [
            account for account in self.ledger.accounts.values() if "suspense" in account.name
        ]
        if len(self.ledger.journal_entries) >= 2 and any(account.balance for account in suspense_accounts):
            self._add_risk(1, "Suspense account still has a balance.")

        if self.objectives.get("required_documents_attached") or self.objectives.get("all_entries_documented"):
            self._add_risk(1, f"{entry.entry_id} has no supporting document yet.")

    def _audit_document_attachment(
        self, document: SupportingDocument, entry: JournalEntry
    ) -> list[str]:
        warnings: list[str] = []
        if document.period != entry.period:
            warning = f"Document period {document.period} does not match entry period {entry.period}."
            warnings.append(warning)
            self._add_risk(2, warning)
        if document.amount not in {entry.total_debit, entry.total_credit}:
            warning = f"Document amount {document.amount} does not match entry amount {entry.total_debit}."
            warnings.append(warning)
            self._add_risk(2, warning)
        if document.related_account:
            entry_accounts = {line.account for line in entry.all_lines}
            if document.related_account not in entry_accounts:
                warning = f"Document account {document.related_account} is not in {entry.entry_id}."
                warnings.append(warning)
                self._add_risk(2, warning)
        if not warnings:
            flag = f"{entry.entry_id} has no supporting document yet."
            if flag in self.active_flags:
                self.active_flags.remove(flag)
                self.resolved_flags.append(f"{entry.entry_id} support matched {document.document_id}.")
        return warnings

    def _add_risk(self, amount: int, flag: str) -> None:
        self.audit_risk += amount
        if flag not in self.active_flags:
            self.active_flags.append(flag)

    def _entry_posted_message(self, entry: JournalEntry) -> str:
        debit_text = ", ".join(f"{line.account} {line.amount}" for line in entry.debit_lines)
        credit_text = ", ".join(f"{line.account} {line.amount}" for line in entry.credit_lines)
        return (
            f"Posted {entry.entry_id} for {entry.period}: "
            f"debit {debit_text}; credit {credit_text}. Memo: {entry.memo}"
        )

    def _lock_failures(self) -> list[str]:
        failures: list[str] = []
        if not self.ledger.is_trial_balanced:
            failures.append(
                f"Trial balance is off: debits {self.ledger.total_debits}, credits {self.ledger.total_credits}."
            )
        if self.audit_risk >= self.audit_limit:
            failures.append(f"Audit risk is {self.audit_risk}; it must stay below {self.audit_limit}.")
        if self.commands_left < 0:
            failures.append("Commands left is below zero.")

        for objective in self.objective_statuses():
            if not objective.passed:
                failures.append(f"{objective.name}: {objective.detail}.")
        return failures

    def _record_clear(self, level_id: str) -> None:
        cleared = [str(item) for item in self.save_data.get("cleared_levels", [])]
        if level_id not in cleared:
            cleared.append(level_id)
        self.save_data["cleared_levels"] = cleared

        commands_used = self.command_limit - self.commands_left
        score = {"audit": self.audit_risk, "commands_used": commands_used}
        best_scores = self.save_data.setdefault("best_scores", {})
        previous = best_scores.get(level_id)
        if not isinstance(previous, dict) or (
            score["audit"],
            score["commands_used"],
        ) < (
            int(previous.get("audit", 999999)),
            int(previous.get("commands_used", 999999)),
        ):
            best_scores[level_id] = score

    def _clamped_level_index(self, value: Any) -> int:
        if not isinstance(value, int):
            return 0
        return min(max(value, 0), len(self.levels) - 1)
