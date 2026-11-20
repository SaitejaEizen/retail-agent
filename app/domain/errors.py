"""The single error model (AD-6). Pure: no framework or database imports."""

from enum import StrEnum


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"


DEFAULT_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.VALIDATION_ERROR: "The request is invalid.",
    ErrorCode.DATABASE_UNAVAILABLE: "The database is unavailable.",
    ErrorCode.NOT_FOUND: "The requested resource was not found.",
    ErrorCode.METHOD_NOT_ALLOWED: "This method is not allowed for this resource.",
    ErrorCode.INTERNAL_ERROR: "An unexpected error occurred.",
    ErrorCode.ORDER_NOT_FOUND: "Order not found.",
}


class DomainError(Exception):
    """A failure with a machine-readable code and a human-readable message."""

    def __init__(self, code: ErrorCode, message: str | None = None) -> None:
        self.code = code
        self.message = message or DEFAULT_MESSAGES[code]
        super().__init__(f"{code}: {self.message}")
