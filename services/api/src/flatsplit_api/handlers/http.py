"""HTTP API Lambda: routes requests from API Gateway (HTTP API, payload v2)."""

import json
from typing import Any

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, Response
from aws_lambda_powertools.event_handler.exceptions import NotFoundError
from aws_lambda_powertools.utilities.typing import LambdaContext

from flatsplit_api.errors import ApiError, not_found, validation_failed
from flatsplit_api.models import HealthResponse, PlacesResponse
from flatsplit_api.onemap import (
    OneMapRateLimited,
    OneMapUnavailable,
    find_places,
    normalise_query,
)

logger = Logger()

# CloudFront forwards browser requests as /api/...; local Vite strips the prefix.
app = APIGatewayHttpResolver(strip_prefixes=["/api"], enable_validation=True)

#: docs/api-contract.md: `q` is 3-100 characters.
QUERY_MIN_LENGTH = 3
QUERY_MAX_LENGTH = 100


def _error_response(error: ApiError) -> Response[str]:
    return Response(
        status_code=error.status_code,
        content_type="application/json",
        body=json.dumps(error.body()),
    )


# Powertools does not annotate exception_handler, so mypy sees an untyped
# decorator here.
@app.exception_handler(ApiError)  # type: ignore[untyped-decorator]
def handle_api_error(exc: ApiError) -> Response[str]:
    return _error_response(exc)


@app.not_found
def handle_not_found(_exc: NotFoundError) -> Response[str]:
    # Keeps unknown routes on the contract's single error body.
    return _error_response(not_found("Unknown route."))


@app.get("/health")
def health() -> HealthResponse:
    return HealthResponse()


@app.get("/places")
def places() -> PlacesResponse:
    """Return explicit selectable/unsupported candidates; never auto-select."""
    raw = app.current_event.get_query_string_value(name="q", default_value="") or ""
    if any(ord(char) < 32 or ord(char) == 127 for char in raw):
        raise validation_failed("q", "Control characters are not allowed.")
    query = normalise_query(raw)

    if len(query) < QUERY_MIN_LENGTH:
        raise validation_failed("q", f"Enter at least {QUERY_MIN_LENGTH} characters.")
    if len(query) > QUERY_MAX_LENGTH:
        raise validation_failed("q", f"Use at most {QUERY_MAX_LENGTH} characters.")

    try:
        found = find_places(query)
    except OneMapRateLimited as exc:
        logger.warning("OneMap throttled the lookup")
        raise ApiError(
            429, "RATE_LIMITED", "Too many destination lookups. Try again shortly."
        ) from exc
    except OneMapUnavailable as exc:
        logger.warning("OneMap lookup failed")
        raise ApiError(
            503,
            "UPSTREAM_UNAVAILABLE",
            "Destination search is unavailable. Try again shortly.",
        ) from exc

    return PlacesResponse.model_validate(found)


@logger.inject_lambda_context
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    return app.resolve(event, context)
