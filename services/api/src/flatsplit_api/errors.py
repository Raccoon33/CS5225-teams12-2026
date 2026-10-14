"""The single error body every endpoint returns (docs/api-contract.md)."""

from typing import Any


class ApiError(Exception):
    """Carries the contract's status, code and message to the error handler."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details

    def body(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details is not None:
            error["details"] = self.details
        return {"error": error}


def validation_failed(field: str, message: str) -> ApiError:
    return ApiError(
        422,
        "VALIDATION_FAILED",
        "The request failed validation.",
        [{"field": field, "message": message}],
    )


def not_found(message: str = "Not found.") -> ApiError:
    return ApiError(404, "NOT_FOUND", message)
