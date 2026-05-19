from __future__ import annotations

from dataclasses import dataclass


VALID_SIDES = {"debit", "credit"}
VALID_ACCOUNT_TYPES = {"asset", "liability", "equity", "revenue", "expense", "contra_asset"}
NORMAL_SIDE_BY_TYPE = {
    "asset": "debit",
    "expense": "debit",
    "liability": "credit",
    "equity": "credit",
    "revenue": "credit",
    "contra_asset": "credit",
}


class LedgerError(ValueError):
    """Raised when a ledger operation is invalid."""


def normalize_side(side: str) -> str:
    normalized = side.lower()
    if normalized not in VALID_SIDES:
        raise LedgerError("Side must be debit or credit.")
    return normalized


def normalize_account_type(account_type: str) -> str:
    normalized = account_type.lower()
    if normalized not in VALID_ACCOUNT_TYPES:
        raise LedgerError(
            "Account type must be asset, liability, equity, revenue, expense, or contra_asset."
        )
    return normalized


@dataclass
class Account:
    name: str
    account_type: str
    normal_side: str
    balance: int
    locked: bool = False
    notes: str = ""
    opening_balance: int = 0

    @classmethod
    def from_level(cls, payload: dict) -> "Account":
        name = str(payload["name"]).lower()
        account_type = normalize_account_type(str(payload["type"]))
        if "normal_side" in payload:
            normal_side = normalize_side(str(payload["normal_side"]))
        else:
            normal_side = NORMAL_SIDE_BY_TYPE[account_type]
        balance = int(payload.get("balance", 0))
        return cls(
            name=name,
            account_type=account_type,
            normal_side=normal_side,
            balance=balance,
            locked=bool(payload.get("locked", False)),
            notes=str(payload.get("notes", "")),
            opening_balance=balance,
        )

    def clone(self) -> "Account":
        return Account(
            name=self.name,
            account_type=self.account_type,
            normal_side=self.normal_side,
            balance=self.balance,
            locked=self.locked,
            notes=self.notes,
            opening_balance=self.opening_balance,
        )

    @property
    def display_type(self) -> str:
        return self.account_type.replace("_", " ").title()

    def apply_line(self, side: str, amount: int) -> None:
        side = normalize_side(side)
        if side == self.normal_side:
            self.balance += amount
        else:
            self.balance -= amount

    def presented_balance(self) -> tuple[int, int]:
        return present_balance(self.normal_side, self.balance)


def present_balance(normal_side: str, balance: int) -> tuple[int, int]:
    normal_side = normalize_side(normal_side)
    if normal_side == "debit":
        return (balance, 0) if balance >= 0 else (0, -balance)
    return (0, balance) if balance >= 0 else (-balance, 0)


@dataclass(frozen=True)
class JournalLine:
    side: str
    account: str
    amount: int


@dataclass(frozen=True)
class JournalEntry:
    entry_id: str
    period: str
    debit_lines: tuple[JournalLine, ...]
    credit_lines: tuple[JournalLine, ...]
    memo: str
    document_id: str | None = None

    def with_document(self, document_id: str | None) -> "JournalEntry":
        return JournalEntry(
            entry_id=self.entry_id,
            period=self.period,
            debit_lines=self.debit_lines,
            credit_lines=self.credit_lines,
            memo=self.memo,
            document_id=document_id,
        )

    @property
    def total_debit(self) -> int:
        return sum(line.amount for line in self.debit_lines)

    @property
    def total_credit(self) -> int:
        return sum(line.amount for line in self.credit_lines)

    @property
    def all_lines(self) -> tuple[JournalLine, ...]:
        return self.debit_lines + self.credit_lines


@dataclass(frozen=True)
class AccountLedgerLine:
    entry_id: str
    period: str
    debit_amount: int
    credit_amount: int
    memo: str
    running_balance: int


@dataclass(frozen=True)
class TrialBalanceRow:
    account: str
    account_type: str
    debit_balance: int
    credit_balance: int
    status: str


@dataclass
class Ledger:
    accounts: dict[str, Account]
    journal_entries: list[JournalEntry]

    @classmethod
    def from_level(cls, level: dict) -> "Ledger":
        accounts = {}
        for payload in level["accounts"]:
            account = Account.from_level(payload)
            if account.name in accounts:
                raise LedgerError(f"Duplicate account '{account.name}'.")
            accounts[account.name] = account
        return cls(accounts=accounts, journal_entries=[])

    def clone(self) -> "Ledger":
        return Ledger(
            accounts={name: account.clone() for name, account in self.accounts.items()},
            journal_entries=list(self.journal_entries),
        )

    def resolve_account(self, account: str) -> str:
        requested = account.lower()
        if requested in self.accounts:
            return requested
        raise LedgerError(f"Account '{account}' does not exist.")

    def get_account(self, account: str) -> Account:
        return self.accounts[self.resolve_account(account)]

    def post_entry(
        self,
        entry_id: str,
        period: str,
        debit_lines: list[tuple[str, int]],
        credit_lines: list[tuple[str, int]],
        memo: str,
        *,
        document_id: str | None = None,
        allow_locked: bool = False,
    ) -> JournalEntry:
        entry = self._build_entry(entry_id, period, debit_lines, credit_lines, memo, document_id)
        self._validate_entry(entry, allow_locked=allow_locked)

        for line in entry.all_lines:
            self.accounts[line.account].apply_line(line.side, line.amount)
        self.journal_entries.append(entry)
        return entry

    def attach_document(self, entry_id: str, document_id: str) -> JournalEntry:
        requested = entry_id.lower()
        for index, entry in enumerate(self.journal_entries):
            if entry.entry_id.lower() == requested:
                updated = entry.with_document(document_id.lower())
                self.journal_entries[index] = updated
                return updated
        raise LedgerError(f"Entry '{entry_id}' does not exist.")

    def trial_balance(self) -> list[TrialBalanceRow]:
        rows: list[TrialBalanceRow] = []
        for account in self.accounts.values():
            debit_balance, credit_balance = account.presented_balance()
            status = "normal" if account.balance >= 0 else "abnormal"
            rows.append(
                TrialBalanceRow(
                    account=account.name,
                    account_type=account.display_type,
                    debit_balance=debit_balance,
                    credit_balance=credit_balance,
                    status=status,
                )
            )
        return rows

    @property
    def total_debits(self) -> int:
        return sum(row.debit_balance for row in self.trial_balance())

    @property
    def total_credits(self) -> int:
        return sum(row.credit_balance for row in self.trial_balance())

    @property
    def is_trial_balanced(self) -> bool:
        return self.total_debits == self.total_credits

    def account_ledger(self, account_name: str) -> list[AccountLedgerLine]:
        account = self.get_account(account_name)
        running_balance = account.opening_balance
        lines: list[AccountLedgerLine] = []
        if account.opening_balance:
            debit_amount, credit_amount = present_balance(account.normal_side, account.opening_balance)
            lines.append(
                AccountLedgerLine(
                    entry_id="OPEN",
                    period="opening",
                    debit_amount=debit_amount,
                    credit_amount=credit_amount,
                    memo="Opening balance",
                    running_balance=running_balance,
                )
            )

        running_balance = account.opening_balance
        for entry in self.journal_entries:
            for line in entry.all_lines:
                if line.account != account.name:
                    continue
                if line.side == account.normal_side:
                    running_balance += line.amount
                else:
                    running_balance -= line.amount
                lines.append(
                    AccountLedgerLine(
                        entry_id=entry.entry_id,
                        period=entry.period,
                        debit_amount=line.amount if line.side == "debit" else 0,
                        credit_amount=line.amount if line.side == "credit" else 0,
                        memo=entry.memo,
                        running_balance=running_balance,
                    )
                )
        return lines

    def _build_entry(
        self,
        entry_id: str,
        period: str,
        debit_lines: list[tuple[str, int]],
        credit_lines: list[tuple[str, int]],
        memo: str,
        document_id: str | None,
    ) -> JournalEntry:
        return JournalEntry(
            entry_id=entry_id,
            period=period,
            debit_lines=tuple(self._build_lines("debit", debit_lines)),
            credit_lines=tuple(self._build_lines("credit", credit_lines)),
            memo=memo.strip() or "No memo",
            document_id=document_id,
        )

    def _build_lines(self, side: str, lines: list[tuple[str, int]]) -> list[JournalLine]:
        built_lines: list[JournalLine] = []
        for account_name, amount in lines:
            resolved = self.resolve_account(account_name)
            built_lines.append(JournalLine(side=side, account=resolved, amount=int(amount)))
        return built_lines

    def _validate_entry(self, entry: JournalEntry, *, allow_locked: bool) -> None:
        if not entry.debit_lines:
            raise LedgerError("Journal entry needs at least one debit line.")
        if not entry.credit_lines:
            raise LedgerError("Journal entry needs at least one credit line.")
        if entry.total_debit != entry.total_credit:
            raise LedgerError(
                f"Entry is unbalanced: debits {entry.total_debit}, credits {entry.total_credit}."
            )
        for line in entry.all_lines:
            if line.amount <= 0:
                raise LedgerError("Journal entry amounts must be positive integers.")
            account = self.accounts[line.account]
            if account.locked and not allow_locked:
                raise LedgerError(f"Account '{account.name}' is locked and cannot be modified.")