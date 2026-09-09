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


def _payload(payload_id: str) -> dict[str, Any]:
    for filename in ("fnol_edge.json", "fnol_invalid.json", "fnol_valid.json"):
        rows = cast(list[dict[str, Any]], json.loads((DATA_DIR / filename).read_text()))
        for entry in rows:
            if entry["id"] == payload_id:
                return dict(cast(dict[str, Any], entry["payload"]))
    raise KeyError(payload_id)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(StubPolicyClient(), NotificationRepository()))


def test_accepted_notification_returns_201_with_contract_reference(client: TestClient) -> None:
    response = client.post("/notifications", json=_payload("EDGE-01"))
    assert response.status_code == 201
    body = response.json()
    assert CLAIM_REFERENCE.fullmatch(body["claim_reference"])
    assert body["status"] == "recorded"


@pytest.mark.parametrize(
    ("payload_id", "code", "status"),
    [
        ("EDGE-07", "POLICY_NOT_FOUND", 422),
        ("EDGE-05", "LOSS_BEFORE_INCEPTION", 422),
        ("INVALID-03", "LOSS_AFTER_EXPIRY", 422),
        ("EDGE-06", "AMOUNT_EXCEEDS_LIMIT", 422),
        ("EDGE-09", "TYPE_NOT_COVERED", 422),
        ("EDGE-04", "POLICY_CANCELLED", 422),
    ],
    ids=["V-1", "V-2", "V-3", "V-4", "V-5", "V-7"],
)
def test_each_rule_is_reachable_over_http(
    client: TestClient, payload_id: str, code: str, status: int
) -> None:
    response = client.post("/notifications", json=_payload(payload_id))
    assert response.status_code == status
    body = response.json()
    assert body["code"] == code
    assert "message" in body
    assert isinstance(body["detail"], dict)


def test_v1_is_distinguishable_from_policy_master_failures(client: TestClient) -> None:
    response = client.post("/notifications", json=_payload("EDGE-07"))
    body = response.json()
    assert response.status_code == 422
    assert body["code"] == "POLICY_NOT_FOUND"
    assert body["code"] not in POLICY_MASTER_CODES
    assert response.status_code < 500


def test_v6_rejects_a_matching_recorded_notification(client: TestClient) -> None:
    first = client.post("/notifications", json=_payload("VALID-01"))
    assert first.status_code == 201
    response = client.post("/notifications", json=_payload("INVALID-06"))
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "DUPLICATE_NOTIFICATION"
    assert body["detail"]["claim_reference"] == first.json()["claim_reference"]


def test_missing_required_field_returns_400_not_a_rule_code(client: TestClient) -> None:
    response = client.post("/notifications", json=_payload("EDGE-08"))
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "MALFORMED_REQUEST"
    assert body["code"] not in RULE_CODES


def test_extra_field_is_rejected_not_ignored(client: TestClient) -> None:
    body = _payload("EDGE-01")
    body["extra_field"] = "nope"
    response = client.post("/notifications", json=body)
    assert response.status_code == 400
    assert response.json()["code"] == "MALFORMED_REQUEST"


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
    response = client.post("/notifications", json=_payload("EDGE-01"))
    assert response.status_code == status
    assert response.status_code >= 500
    body = response.json()
    assert body["code"] == code
    assert body["detail"]["reason"] == reason
    assert body["detail"]["dependency"] == "policy_master"
