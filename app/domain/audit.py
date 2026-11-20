"""Audit trail vocabulary and email masking (FR7, AD-5). Pure: no I/O."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

EMAIL_PATTERN = re.compile(r"[^\s@\"']*@[^\s@\"']+")


class AuditAction(StrEnum):
    ORDER_LOOKUP = "ORDER_LOOKUP"
    RETURN_REQUESTED = "RETURN_REQUESTED"
    REFUND_CALCULATED = "REFUND_CALCULATED"
    RESTOCK_APPLIED = "RESTOCK_APPLIED"


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    REJECTED = "rejected"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class AuditEntry:
    id: int
    created_at: datetime
    action: AuditAction
    outcome: AuditOutcome
    order_id: str | None
    masked_email: str | None
    details: Mapping[str, Any] = field(default_factory=dict)


def mask_email(email: str) -> str:
    """Keep the first character of the local part and the domain: a***@example.com."""
    local, at, domain = email.strip().lower().partition("@")
    if not at or not local or not domain:
        return "***"
    return f"{local[0]}***@{domain}"


def redact_emails(value: Any) -> Any:
    """Return a copy of ``value`` with every email-looking substring masked."""
    if isinstance(value, str):
        return EMAIL_PATTERN.sub(lambda match: mask_email(match.group(0)), value)
    if isinstance(value, Mapping):
        return {key: redact_emails(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [redact_emails(item) for item in value]
    return value
