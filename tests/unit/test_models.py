from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from claims.models import (
    ClaimRecord,
    NotificationRequest,
    Policy,
    RuleFailure,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
FAILS_AT_MODEL = frozenset({"EDGE-08", "EDGE-11", "EDGE-12"})
FAIL_AT_MODEL_IDS = {
    "EDGE-08": "missing_estimated_amount",
    "EDGE-11": "claim_type_outside_vocabulary",
    "EDGE-12": "amount_three_decimal_places",
}
CATALOG_FILES = ("fnol_edge.json", "fnol_invalid.json")


def _catalog() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for filename in CATALOG_FILES:
        loaded = json.loads((DATA_DIR / filename).read_text())
        rows.extend(cast(list[dict[str, Any]], loaded))
    return rows


def _by_id(payload_id: str) -> dict[str, Any]:
    for entry in _catalog():
        if entry["id"] == payload_id:
            return dict(cast(dict[str, Any], entry["payload"]))
    raise KeyError(payload_id)


def _params(*, fail_at_model: bool) -> list[Any]:
    params: list[Any] = []
    for entry in _catalog():
        payload_id = cast(str, entry["id"])
        if (payload_id in FAILS_AT_MODEL) is fail_at_model:
            case_id = FAIL_AT_MODEL_IDS.get(payload_id, payload_id)
            params.append(
                pytest.param(cast(dict[str, Any], entry["payload"]), id=case_id)
            )
    return params


def _edge_01(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = dict(_by_id("EDGE-01"))
    body.update(overrides)
    return body


def _without(field: str) -> dict[str, object]:
    return {key: value for key, value in _edge_01().items() if key != field}


def _claim_fields(**overrides: object) -> dict[str, object]:
    request = _by_id("EDGE-01")
    body: dict[str, object] = {
        "claim_reference": "CLM-2026-000317",
        "policy_number": request["policy_number"],
        "loss_date": date.fromisoformat(cast(str, request["loss_date"])),
        "claim_type": request["claim_type"],
        "estimated_amount": Decimal(cast(str, request["estimated_amount"])),
        "description": request["description"],
    }
    body.update(overrides)
    return body


def _claim_without(field: str) -> dict[str, object]:
    return {key: value for key, value in _claim_fields().items() if key != field}


def _policy_fields(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "policy_number": "MOT-4479",
        "product": "personal_auto_standard",
        "effective_date": date(2026, 3, 15),
        "expiry_date": date(2027, 3, 14),
        "cancellation_date": None,
        "limit": Decimal("50000.00"),
        "permitted_claim_types": ("collision",),
    }
    body.update(overrides)
    return body


def _policy_without(field: str) -> dict[str, object]:
    return {key: value for key, value in _policy_fields().items() if key != field}


@pytest.mark.parametrize("payload", _params(fail_at_model=False))
def test_catalog_payloads_survive_to_the_rules(payload: dict[str, Any]) -> None:
    request = NotificationRequest.model_validate(payload)
    assert isinstance(request.loss_date, date)
    assert isinstance(request.estimated_amount, Decimal)


@pytest.mark.parametrize("payload", _params(fail_at_model=True))
def test_catalog_payloads_fail_at_the_model(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        _edge_01(policy_number=""),
        _without("policy_number"),
        _without("loss_date"),
        _without("claim_type"),
        _without("estimated_amount"),
        {**_edge_01(), "extra_field": "nope"},
        _edge_01(estimated_amount="0.00"),
        _edge_01(estimated_amount="-1.00"),
        _edge_01(claim_type=""),
        _edge_01(loss_date="02-04-2026"),
        _edge_01(loss_date=datetime(2026, 3, 15)),
        _edge_01(policy_number=4479),
        _edge_01(description=1),
    ],
    ids=[
        "empty_policy_number",
        "missing_policy_number",
        "missing_loss_date",
        "missing_claim_type",
        "missing_estimated_amount",
        "unknown_field",
        "amount_zero",
        "amount_negative",
        "empty_claim_type",
        "loss_date_not_iso",
        "loss_date_datetime_object",
        "policy_number_wrong_type",
        "description_wrong_type",
    ],
)
def test_notification_request_rejects_malformed_payloads(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(payload)


@pytest.mark.parametrize(
    "raw, expected",
    [
        (_by_id("EDGE-01"), "Loss on the day cover attaches."),
        (_without("description"), None),
        ({**_by_id("EDGE-01"), "description": None}, None),
    ],
    ids=["description_present", "description_absent", "description_null"],
)
def test_description_absent_and_null_are_equivalent(
    raw: dict[str, Any], expected: str | None
) -> None:
    request = NotificationRequest.model_validate(raw)
    assert request.description == expected


def test_rule_failure_keeps_rule_and_code_distinct() -> None:
    failure = RuleFailure(rule="V-2", code="LOSS_BEFORE_INCEPTION")
    assert failure.rule == "V-2"
    assert failure.code == "LOSS_BEFORE_INCEPTION"


def test_rule_failure_is_immutable() -> None:
    failure = RuleFailure(rule="V-1", code="POLICY_NOT_FOUND")
    field = "code"
    with pytest.raises(FrozenInstanceError):
        setattr(failure, field, "TYPE_NOT_COVERED")


@pytest.mark.parametrize(
    "cancellation_date",
    [None, date(2026, 2, 1)],
    ids=["not_cancelled", "cancelled"],
)
def test_policy_term_fields_are_dates_and_limit_is_decimal(
    cancellation_date: date | None,
) -> None:
    policy = Policy(
        policy_number="MOT-4479",
        product="personal_auto_standard",
        effective_date=date(2026, 3, 15),
        expiry_date=date(2027, 3, 14),
        cancellation_date=cancellation_date,
        limit=Decimal("50000.00"),
        permitted_claim_types=("collision", "theft", "glass", "liability", "weather"),
    )
    assert isinstance(policy.effective_date, date)
    assert isinstance(policy.expiry_date, date)
    assert isinstance(policy.limit, Decimal)
    assert policy.cancellation_date is cancellation_date or isinstance(
        policy.cancellation_date, date
    )


@pytest.mark.parametrize(
    "fields",
    [
        _policy_without("cancellation_date"),
        _policy_without("policy_number"),
        _policy_without("product"),
        _policy_without("effective_date"),
        _policy_without("expiry_date"),
        _policy_without("limit"),
        _policy_without("permitted_claim_types"),
        {**_policy_fields(), "extra_field": "nope"},
        _policy_fields(policy_number=""),
        _policy_fields(limit=Decimal("0.00")),
        _policy_fields(limit=Decimal("50000.0")),
        _policy_fields(permitted_claim_types=("flood",)),
    ],
    ids=[
        "missing_cancellation_date",
        "missing_policy_number",
        "missing_product",
        "missing_effective_date",
        "missing_expiry_date",
        "missing_limit",
        "missing_permitted_claim_types",
        "unknown_field",
        "empty_policy_number",
        "limit_zero",
        "limit_one_decimal_place",
        "permitted_claim_type_outside_vocabulary",
    ],
)
def test_policy_rejects_constraint_violations(fields: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Policy.model_validate(fields)


def test_claim_record_requires_contract_reference_format() -> None:
    recorded = ClaimRecord.model_validate(_claim_fields())
    assert recorded.claim_reference == "CLM-2026-000317"
    assert isinstance(recorded.loss_date, date)
    assert isinstance(recorded.estimated_amount, Decimal)


@pytest.mark.parametrize(
    "fields",
    [
        _claim_fields(claim_reference="CLM-26-000317"),
        _claim_fields(claim_reference="CLM-2026-317"),
        _claim_fields(claim_reference="2026-000317"),
        {**_claim_fields(), "extra_field": "nope"},
        _claim_fields(policy_number=""),
        _claim_fields(estimated_amount=Decimal("0.00")),
        _claim_fields(estimated_amount=Decimal("5000.0")),
        _claim_fields(claim_type="flood"),
        _claim_without("loss_date"),
        _claim_without("estimated_amount"),
    ],
    ids=[
        "year_not_four_digits",
        "sequence_not_six_digits",
        "missing_prefix",
        "unknown_field",
        "empty_policy_number",
        "amount_zero",
        "amount_one_decimal_place",
        "claim_type_outside_vocabulary",
        "missing_loss_date",
        "missing_estimated_amount",
    ],
)
def test_claim_record_rejects_constraint_violations(
    fields: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(fields)