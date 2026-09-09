"""HTTP surface for the claims intake service.

This layer does three things and no more: it parses the request, it calls the
service, and it maps the outcome to a status code. It holds no rule logic. A rule
that appears here is a rule the service layer cannot be tested for.

Day 4 lab. Implement against `docs/api-contract.md` sections 5 and 6.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from claims.models import NotificationRequest
from claims.policy_client import (
    LookupFailureReason,
    PolicyClient,
    PolicyLookupFailed,
    StubPolicyClient,
)
from claims.repository import NotificationRepository
from claims.service import submit_notification

STATUS_BY_CODE: dict[str, int] = {
    "MALFORMED_REQUEST": 400,
    "POLICY_NOT_FOUND": 422,
    "LOSS_BEFORE_INCEPTION": 422,
    "POLICY_CANCELLED": 422,
    "LOSS_AFTER_EXPIRY": 422,
    "AMOUNT_EXCEEDS_LIMIT": 422,
    "TYPE_NOT_COVERED": 422,
    "DUPLICATE_NOTIFICATION": 409,
    "POLICY_MASTER_TIMEOUT": 504,
    "POLICY_MASTER_UNREACHABLE": 503,
    "POLICY_MASTER_UNPARSABLE": 502,
}

MESSAGE_BY_CODE: dict[str, str] = {
    "MALFORMED_REQUEST": "The request could not be interpreted.",
    "POLICY_NOT_FOUND": "No policy was found with that policy number.",
    "LOSS_BEFORE_INCEPTION": "The loss date precedes the policy effective date.",
    "POLICY_CANCELLED": "The policy was cancelled before the loss date.",
    "LOSS_AFTER_EXPIRY": "The loss date falls after the policy expiry date.",
    "AMOUNT_EXCEEDS_LIMIT": "The estimated amount exceeds the policy limit.",
    "TYPE_NOT_COVERED": "The claim type is not permitted on the policy.",
    "DUPLICATE_NOTIFICATION": "A notification for this loss has already been recorded.",
    "POLICY_MASTER_TIMEOUT": "The policy master did not respond in time.",
    "POLICY_MASTER_UNREACHABLE": "The policy master could not be reached.",
    "POLICY_MASTER_UNPARSABLE": "The policy master returned a body this service could not parse.",
}

LOOKUP_FAILURE: dict[LookupFailureReason, str] = {
    "timeout": "POLICY_MASTER_TIMEOUT",
    "unreachable": "POLICY_MASTER_UNREACHABLE",
    "unparsable": "POLICY_MASTER_UNPARSABLE",
}

_ISSUE_BY_PYDANTIC_TYPE: dict[str, str] = {
    "missing": "required_field_absent",
    "extra_forbidden": "unknown_field",
}


def _jsonable(value: object) -> object:
    """Turn rule-detail values into types json.dumps accepts, without losing cents."""
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _jsonable_detail(detail: dict[str, Any]) -> dict[str, Any]:
    return {key: _jsonable(value) for key, value in detail.items()}


def _envelope(code: str, detail: dict[str, Any]) -> JSONResponse:
    return JSONResponse(
        status_code=STATUS_BY_CODE[code],
        content={
            "code": code,
            "message": MESSAGE_BY_CODE[code],
            "detail": _jsonable_detail(detail),
        },
    )


def _malformed(field: str | None, issue: str) -> JSONResponse:
    return _envelope("MALFORMED_REQUEST", {"field": field, "issue": issue})


def _from_validation_error(exc: ValidationError) -> JSONResponse:
    error = exc.errors()[0]
    loc = error["loc"]
    field = str(loc[-1]) if loc else None
    issue = _ISSUE_BY_PYDANTIC_TYPE.get(error["type"], error["type"])
    return _malformed(field, issue)


def create_app(
    policy_client: PolicyClient | None = None,
    repository: NotificationRepository | None = None,
) -> FastAPI:
    """Build an app with injected dependencies."""
    resolved_client = policy_client or StubPolicyClient()
    resolved_repository = repository or NotificationRepository()
    application = FastAPI(title="Claims Intake Service")
    application.state.policy_client = resolved_client
    application.state.repository = resolved_repository

    @application.post("/notifications")
    async def post_notification(request: Request) -> JSONResponse:
        try:
            body: object = json.loads(await request.body())
        except json.JSONDecodeError:
            return _malformed(None, "body_not_json")
        if not isinstance(body, dict):
            return _malformed(None, "body_not_json")

        try:
            notification = NotificationRequest.model_validate(body)
        except ValidationError as exc:
            return _from_validation_error(exc)

        try:
            outcome = submit_notification(
                notification, resolved_client, resolved_repository
            )
        except PolicyLookupFailed as exc:
            return _envelope(
                LOOKUP_FAILURE[exc.reason],
                {"dependency": "policy_master", "reason": exc.reason},
            )

        if outcome.passed:
            return JSONResponse(
                status_code=201,
                content={
                    "claim_reference": outcome.claim_reference,
                    "status": "recorded",
                },
            )
        assert outcome.code is not None
        return _envelope(outcome.code, outcome.detail)

    return application


app = create_app()
