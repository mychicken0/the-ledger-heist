from __future__ import annotations

from dataclasses import dataclass
from typing import Any


VALID_DOCUMENT_TYPES = {
    "invoice",
    "receipt",
    "bank_slip",
    "contract",
    "purchase_order",
    "audit_note",
    "timesheet",
    "schedule",
    "memo",
    "resolution",
    "statement",
}


class DocumentError(ValueError):
    """Raised when a supporting document is invalid or missing."""


@dataclass(frozen=True)
class SupportingDocument:
    document_id: str
    document_type: str
    amount: int
    related_account: str | None
    period: str
    description: str

    @classmethod
    def from_level(cls, payload: dict[str, Any]) -> "SupportingDocument":
        document_id = str(payload["id"]).lower()
        document_type = str(payload["type"]).lower()
        if document_type not in VALID_DOCUMENT_TYPES:
            raise DocumentError(f"Unsupported document type '{document_type}'.")
        amount = int(payload["amount"])
        if amount < 0:
            raise DocumentError("Document amount must be nonnegative.")
        related_account = payload.get("related_account")
        return cls(
            document_id=document_id,
            document_type=document_type,
            amount=amount,
            related_account=str(related_account).lower() if related_account else None,
            period=str(payload["period"]),
            description=str(payload.get("description", "")),
        )
