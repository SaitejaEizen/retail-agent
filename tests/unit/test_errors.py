from app.domain.errors import DEFAULT_MESSAGES, DomainError, ErrorCode


def test_domain_error_carries_code_and_default_message() -> None:
    """NFR3 / AD-6: a DomainError has a machine-readable code and a readable message."""
    err = DomainError(ErrorCode.DATABASE_UNAVAILABLE)
    assert err.code is ErrorCode.DATABASE_UNAVAILABLE
    assert err.message == "The database is unavailable."


def test_domain_error_custom_message() -> None:
    """NFR3 / AD-6: callers can give a more specific message."""
    assert DomainError(ErrorCode.VALIDATION_ERROR, "bad email").message == "bad email"


def test_every_code_has_a_default_message() -> None:
    """NFR3 / AD-6: no error code is left without a human-readable message."""
    assert set(DEFAULT_MESSAGES) == set(ErrorCode)
