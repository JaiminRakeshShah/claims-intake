from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from claims.models import ClaimRecord, NotificationRequest
from claims.repository import NotificationRepository

CLAIM_REFERENCE = re.compile(r"^CLM-\d{4}-\d{6}$")
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture
def repository() -> NotificationRepository:
    return NotificationRepository()


@pytest.fixture
def notification() -> NotificationRequest:
    entries = cast(
        list[dict[str, Any]],
        json.loads((DATA_DIR / "fnol_edge.json").read_text()),
    )
    for entry in entries:
        if entry["id"] == "EDGE-01":
            return NotificationRequest.model_validate(entry["payload"])
    raise KeyError("EDGE-01")


def _as_claim(
    repository: NotificationRepository,
    notification: NotificationRequest,
    **overrides: object,
) -> ClaimRecord:
    """A ClaimRecord is what the store accepts. Issue the reference first."""
    body: dict[str, object] = {
        "claim_reference": repository.issue_claim_reference(),
        "policy_number": notification.policy_number,
        "loss_date": notification.loss_date,
        "claim_type": notification.claim_type,
        "estimated_amount": notification.estimated_amount,
        "description": notification.description,
    }
    body.update(overrides)
    return ClaimRecord.model_validate(body)


def test_issue_claim_reference_matches_contract_format(
    repository: NotificationRepository,
) -> None:
    assert CLAIM_REFERENCE.fullmatch(repository.issue_claim_reference())


def test_issued_claim_references_are_never_reissued(
    repository: NotificationRepository,
) -> None:
    first = repository.issue_claim_reference()
    second = repository.issue_claim_reference()
    assert first != second


def test_record_returns_a_contract_claim_reference(
    repository: NotificationRepository,
    notification: NotificationRequest,
) -> None:
    recorded = repository.record(_as_claim(repository, notification))
    assert CLAIM_REFERENCE.fullmatch(recorded.claim_reference)
    assert recorded.policy_number == notification.policy_number
    assert recorded.loss_date == notification.loss_date
    assert recorded.claim_type == notification.claim_type
    assert recorded.estimated_amount == notification.estimated_amount


def test_recorded_claim_references_are_unique(
    repository: NotificationRepository,
    notification: NotificationRequest,
) -> None:
    first = repository.record(_as_claim(repository, notification))
    second = repository.record(
        _as_claim(
            repository,
            notification.model_copy(update={"loss_date": date(2026, 3, 16)}),
        )
    )
    assert first.claim_reference != second.claim_reference


def test_find_matching_returns_the_recorded_claim(
    repository: NotificationRepository,
    notification: NotificationRequest,
) -> None:
    recorded = repository.record(_as_claim(repository, notification))
    found = repository.find_matching(
        notification.policy_number,
        notification.loss_date,
        notification.claim_type,
    )
    assert found is not None
    assert found.claim_reference == recorded.claim_reference


@pytest.mark.parametrize(
    "field, value",
    [
        ("policy_number", "MOT-4472"),
        ("loss_date", date(2026, 3, 16)),
        ("claim_type", "theft"),
    ],
    ids=[
        "same_date_and_type_different_policy",
        "same_policy_and_type_different_date",
        "same_policy_and_date_different_type",
    ],
)
def test_agreement_on_only_two_fields_is_not_a_duplicate(
    repository: NotificationRepository,
    notification: NotificationRequest,
    field: str,
    value: object,
) -> None:
    repository.record(_as_claim(repository, notification))
    differing = notification.model_copy(update={field: value})
    assert (
        repository.find_matching(
            differing.policy_number,
            differing.loss_date,
            differing.claim_type,
        )
        is None
    )


def test_resubmitting_a_rejected_notification_is_not_a_duplicate(
    repository: NotificationRepository,
    notification: NotificationRequest,
) -> None:
    # Same three match keys, but estimated_amount omitted so the model refuses.
    refused: dict[str, object] = {
        "policy_number": notification.policy_number,
        "loss_date": notification.loss_date,
        "claim_type": notification.claim_type,
        "description": notification.description,
    }
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(refused)

    assert (
        repository.find_matching(
            notification.policy_number,
            notification.loss_date,
            notification.claim_type,
        )
        is None
    )

    recorded = repository.record(_as_claim(repository, notification))
    found = repository.find_matching(
        notification.policy_number,
        notification.loss_date,
        notification.claim_type,
    )
    assert found is recorded