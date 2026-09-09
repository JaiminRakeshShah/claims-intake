from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from claims.api.routes import create_app
from claims.policy_client import StubPolicyClient
from claims.repository import NotificationRepository

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


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(StubPolicyClient(), NotificationRepository()))


def test_v1_is_distinguishable_from_policy_master_failures(client: TestClient) -> None:
    response = client.post("/notifications", json=_edge("EDGE-07"))
    body = response.json()
    assert response.status_code == 422
    assert body["code"] == "POLICY_NOT_FOUND"
    assert body["code"] not in POLICY_MASTER_CODES
    assert response.status_code < 500


def test_extra_field_is_rejected_not_ignored(client: TestClient) -> None:
    body = _edge("EDGE-01")
    body["extra_field"] = "nope"
    response = client.post("/notifications", json=body)
    assert response.status_code == 400
    detail = response.json()
    assert detail["code"] == "MALFORMED_REQUEST"
    assert detail["detail"]["field"] == "extra_field"
    assert detail["detail"]["issue"] == "unknown_field"


def test_empty_policy_number_is_malformed_not_v1(client: TestClient) -> None:
    body = _edge("EDGE-01")
    body["policy_number"] = ""
    response = client.post("/notifications", json=body)
    assert response.status_code == 400
    detail = response.json()
    assert detail["code"] == "MALFORMED_REQUEST"
    assert detail["code"] != "POLICY_NOT_FOUND"
    assert detail["detail"]["field"] == "policy_number"
    assert isinstance(detail["detail"]["issue"], str)


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
