# The Ledger Heist

The Ledger Heist is a terminal accounting puzzle game built with Python and Textual.

You solve safe accounting simulations by posting balanced journal entries, reviewing account ledgers, checking a trial balance, and clearing audit-style objectives. The game is educational and puzzle-like; it is not financial advice and does not provide real-world fraud instructions.

## Requirements

- Python 3.11+
- textual
- rich
- pyinstaller

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
```

## Run

```powershell
python main.py
```

If Windows cannot find `python` after activation, run:

```powershell
.\.venv\Scripts\python.exe main.py
```

## Build The EXE

```powershell
build_tools\build_exe.bat
```

The executable is created at:

```text
dist\TheLedgerHeist.exe
```

## Command Guide

```text
help
scan
accounts
list
rules
entry debit <account> <amount> credit <account> <amount> [memo text]
entry debit.<account>(amount) credit.<account>(amount) [memo text]
debit.<account>(amount) credit.<account>(amount) [memo text]
ledger <account>
trial
docs
inspect <document_id>
attach <document_id> <entry_id>
lock
undo
restart
exit
```

`list` is an alias for `accounts`. The older `adjust` and `siphon` commands now show guidance to use journal entries.

## Journal Entry Examples

```text
debit.cash(100) credit.service_revenue(100) sale recorded
debit.cash(500) credit.loan_payable(500) bank loan
debit.rent_expense(50) credit.cash(50) paid rent
debit.suspense(50) credit.service_revenue(50) clear suspense
```

Every journal entry must balance: total debits must equal total credits. Amounts are positive integers, accounts must exist, locked accounts cannot be changed, and the period must be open.

## Accounting Basics In The Game

Accounts have a type and a normal side:

- Assets normally increase with debits.
- Expenses normally increase with debits.
- Liabilities normally increase with credits.
- Equity normally increases with credits.
- Revenue normally increases with credits.

The game stores balances as normal-side balances. A negative balance appears on the opposite side of the trial balance and may raise audit attention.

## Trial Balance

Use:

```text
trial
```

The trial balance lists each account with a debit or credit balance and totals both sides. A level can only lock when the trial balance is balanced and the level objectives pass.

## Account Ledger

Use:

```text
ledger cash
```

This shows one account's history: entry id, period, debit amount, credit amount, memo, and running balance.

## Audit And Objectives

Use:

```text
scan
rules
```

`scan` shows the current period, trial balance status, audit risk, command budget, objectives, and red flags. `rules` shows the level goals. Audit risk can increase for invalid entries, failed lock attempts, locked-account edits, and repeated suspicious patterns.

## Supporting Documents

Use:

```text
docs
inspect inv-410
attach inv-410 JE-0001
```

Documents are audit support such as invoices, receipts, bank slips, contracts, purchase orders, and audit notes. Some levels require entries to be attached to a matching document before `lock` succeeds. A mismatch in amount, period, or related account raises audit risk.

## Phase Roadmap

Phase 1 includes account types, journal entries, account ledgers, trial balance, objectives, and a refreshed Textual UI.

Phase 2 adds supporting documents with `docs`, `inspect`, and `attach`.

Future phases can add period close/reversal, financial statements, bank reconciliation, accrual/deferred tutorial levels, and a fuller audit system.

## Save Data

Progress is stored in:

```text
saves\save.json
```

The save file tracks the last level, cleared levels, and best scores. When running from a PyInstaller build, saves are written next to the executable so bundled data files remain read-only.

## Safety Note

This is an accounting puzzle and learning simulation. It is not real financial, legal, tax, audit, or compliance advice.
