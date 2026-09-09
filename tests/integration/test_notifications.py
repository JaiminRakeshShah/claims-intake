from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from claims.api.routes import create_app
from claims.policy_client import LookupFailureReason, StubPolicyClient
from claims.repository import NotificationRepository

CLAIM_REFERENCE = re.compile(r"^CLM-\d{4}-\d{6}$")
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
POLICY_MASTER_CODES = frozenset(
    {
        "POLICY_MASTER_TIMEOUT",
        "POLICY_MASTER_UNREACHABLE",
        "POLICY_MASTER_UNPARSABLE",
    }
)
RULE_CODES = frozenset(
    {
        "POLICY_NOT_FOUND",
        "LOSS_BEFORE_INCEPTION",
        "LOSS_AFTER_EXPIRY",
        "AMOUNT_EXCEEDS_LIMIT",
        "TYPE_NOT_COVERED",
        "DUPLICATE_NOTIFICATION",
        "POLICY_CANCELLED",
    }
)


def _payload(filename: str, payload_id: str) -> dict[str, Any]:
    rows = cast(list[dict[str, Any]], json.loads((DATA_DIR / filename).read_text()))
    for entry in rows:
        if entry["id"] == payload_id:
            return dict(cast(dict[str, Any], entry["payload"]))
    raise KeyError(payload_id)


def _edge(payload_id: str) -> dict[str, Any]:
    return _payload("fnol_edge.json", payload_id)


def _invalid(payload_id: str) -> dict[str, Any]:
    return _payload("fnol_invalid.json", payload_id)


def _valid(payload_id: str) -> dict[str, Any]:
    return _payload("fnol_valid.json", payload_id)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(StubPolicyClient(), NotificationRepository()))


def test_accepted_notification_returns_201_with_contract_reference(client: TestClient) -> None:
    response = client.post("/notifications", json=_edge("EDGE-01"))
    assert response.status_code == 201
    body = response.json()
    assert CLAIM_REFERENCE.fullmatch(body["claim_reference"])
    assert body["status"] == "recorded"


@pytest.mark.parametrize(
    ("payload", "code", "status", "detail"),
    [
        (
            _edge("EDGE-07"),
            "POLICY_NOT_FOUND",
            422,
            {"policy_number": "mot-4471"},
        ),
        (
            _edge("EDGE-05"),
            "LOSS_BEFORE_INCEPTION",
            422,
            {"loss_date": "2026-03-02", "effective_date": "2026-04-15"},
        ),
        (
            _invalid("INVALID-03"),
            "LOSS_AFTER_EXPIRY",
            422,
            {"loss_date": "2026-03-20", "expiry_date": "2026-02-28"},
        ),
        (
            _edge("EDGE-06"),
            "AMOUNT_EXCEEDS_LIMIT",
            422,
            {"estimated_amount": "26000.00", "limit": "10000.00"},
        ),
        (
            _edge("EDGE-09"),
            "TYPE_NOT_COVERED",
            422,
            {
                "claim_type": "collision",
                "permitted_claim_types": ["theft", "glass", "weather", "liability"],
            },
        ),
        (
            _edge("EDGE-04"),
            "POLICY_CANCELLED",
            422,
            {"loss_date": "2026-01-15", "cancellation_date": "2026-01-15"},
        ),
    ],
    ids=["V-1", "V-2", "V-3", "V-4", "V-5", "V-7"],
)
def test_each_rule_is_reachable_over_http(
    client: TestClient,
    payload: dict[str, Any],
    code: str,
    status: int,
    detail: dict[str, Any],
) -> None:
    response = client.post("/notifications", json=payload)
    assert response.status_code == status
    body = response.json()
    assert body["code"] == code
    assert "message" in body
    assert body["detail"] == detail


def test_v1_is_distinguishable_from_policy_master_failures(client: TestClient) -> None:
    response = client.post("/notifications", json=_edge("EDGE-07"))
    body = response.json()
    assert response.status_code == 422
    assert body["code"] == "POLICY_NOT_FOUND"
    assert body["code"] not in POLICY_MASTER_CODES
    assert response.status_code < 500


def test_v6_rejects_a_matching_recorded_notification(client: TestClient) -> None:
    first = client.post("/notifications", json=_valid("VALID-01"))
    assert first.status_code == 201
    response = client.post("/notifications", json=_invalid("INVALID-06"))
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "DUPLICATE_NOTIFICATION"
    assert body["detail"]["claim_reference"] == first.json()["claim_reference"]


def test_missing_required_field_returns_400_not_a_rule_code(client: TestClient) -> None:
    response = client.post("/notifications", json=_edge("EDGE-08"))
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "MALFORMED_REQUEST"
    assert body["code"] not in RULE_CODES
    assert body["detail"]["field"] == "estimated_amount"
    assert body["detail"]["issue"] == "required_field_absent"


def test_extra_field_is_rejected_not_ignored(client: TestClient) -> None:
    body = _edge("EDGE-01")
    body["extra_field"] = "nope"
    response = client.post("/notifications", json=body)
    assert response.status_code == 400
    detail = response.json()
    assert detail["code"] == "MALFORMED_REQUEST"
    assert detail["detail"]["field"] == "extra_field"
    assert detail["detail"]["issue"] == "unknown_field"


def test_body_not_json_returns_malformed_request(client: TestClient) -> None:
    response = client.post(
        "/notifications",
        content=b"not-json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "MALFORMED_REQUEST"
    assert body["detail"]["field"] is None
    assert body["detail"]["issue"] == "body_not_json"


def test_claim_type_outside_vocabulary_is_malformed(client: TestClient) -> None:
    response = client.post("/notifications", json=_edge("EDGE-11"))
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "MALFORMED_REQUEST"
    assert body["code"] not in RULE_CODES
    assert body["detail"]["field"] == "claim_type"
    assert isinstance(body["detail"]["issue"], str)


def test_amount_wrong_scale_is_malformed(client: TestClient) -> None:
    response = client.post("/notifications", json=_edge("EDGE-12"))
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "MALFORMED_REQUEST"
    assert body["code"] not in RULE_CODES
    assert body["detail"]["field"] == "estimated_amount"
    assert isinstance(body["detail"]["issue"], str)


def test_refused_submission_is_not_a_duplicate(client: TestClient) -> None:
    """WI-0151 AC-3. Nothing was recorded, so a matching retry is not 409."""
    first = client.post("/notifications", json=_edge("EDGE-05"))
    assert first.status_code == 422
    assert first.json()["code"] == "LOSS_BEFORE_INCEPTION"
    second = client.post("/notifications", json=_edge("EDGE-05"))
    assert second.status_code == 422
    assert second.json()["code"] == "LOSS_BEFORE_INCEPTION"
    assert second.status_code != 409


def test_cancelled_and_expired_reports_cancelled(client: TestClient) -> None:
    """WI-0158 AC-4. Cancellation is reported ahead of expiry (EDGE-10)."""
    response = client.post("/notifications", json=_edge("EDGE-10"))
    body = response.json()
    assert response.status_code == 422
    assert body["code"] == "POLICY_CANCELLED"
    assert body["code"] != "LOSS_AFTER_EXPIRY"
    assert body["detail"]["loss_date"] == "2026-01-08"
    assert body["detail"]["cancellation_date"] == "2025-10-01"


@pytest.mark.parametrize(
    ("reason", "code", "status"),
    [
        ("timeout", "POLICY_MASTER_TIMEOUT", 504),
        ("unreachable", "POLICY_MASTER_UNREACHABLE", 503),
        ("unparsable", "POLICY_MASTER_UNPARSABLE", 502),
    ],
    ids=["timeout", "unreachable", "unparsable"],
)
def test_policy_lookup_failure_returns_distinct_5xx(
    reason: LookupFailureReason, code: str, status: int
) -> None:
    client = TestClient(
        create_app(StubPolicyClient(fail_with=reason), NotificationRepository())
    )
    response = client.post("/notifications", json=_edge("EDGE-01"))
    assert response.status_code == status
    assert response.status_code >= 500
    body = response.json()
    assert body["code"] == code
    assert body["detail"]["reason"] == reason
    assert body["detail"]["dependency"] == "policy_master"
