import pytest

from app.domain.audit import mask_email, redact_emails


@pytest.mark.parametrize(
    ("email", "masked"),
    [
        ("asha@example.com", "a***@example.com"),
        ("  ASHA@Example.com ", "a***@example.com"),
        ("b@x.io", "b***@x.io"),
        ("@example.com", "***"),
        ("no-at-sign", "***"),
        ("user@", "***"),
        ("", "***"),
    ],
)
def test_mask_email(email: str, masked: str) -> None:
    """FR7 / AD-5: Audit Entries store a masked email, never the full address."""
    assert mask_email(email) == masked


def test_redact_emails_masks_nested_strings_only() -> None:
    """FR7 / AD-5: any email inside details is masked; other values pass through unchanged."""
    details = {
        "reason": "send to asha@example.com please",
        "lines": [{"line_id": 1, "note": "ben@example.com"}],
        "refund_cents": 1250,
        "flag": True,
        "nothing": None,
    }
    assert redact_emails(details) == {
        "reason": "send to a***@example.com please",
        "lines": [{"line_id": 1, "note": "b***@example.com"}],
        "refund_cents": 1250,
        "flag": True,
        "nothing": None,
    }
