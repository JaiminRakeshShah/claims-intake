from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from claims.models import ClaimRecord, ClaimType, NotificationRequest, Policy
from claims.policy_client import StubPolicyClient
from claims.repository import NotificationRepository
from claims.service import (
    evaluate_amount_within_limit,
    evaluate_claim_type_covered,
    evaluate_loss_after_inception,
    evaluate_loss_before_expiry,
    evaluate_not_duplicate,
    evaluate_notification,
    evaluate_policy_exists,
    evaluate_policy_not_cancelled,
)


def a_notification(**overrides: object) -> NotificationRequest:
    fields: dict[str, object] = {
        "policy_number": "MOT-4479",
        "loss_date": date(2026, 6, 1),
        "claim_type": "collision",
        "estimated_amount": Decimal("5000.00"),
    }
    fields.update(overrides)
    return NotificationRequest.model_validate(fields)


@pytest.fixture
def motor_policy() -> Policy:
    return Policy(
        policy_number="MOT-4479",
        product="personal_auto_standard",
        effective_date=date(2026, 3, 15),
        expiry_date=date(2027, 3, 14),
        cancellation_date=None,
        limit=Decimal("55000.00"),
        permitted_claim_types=("collision", "theft", "glass", "liability", "weather"),
    )


@pytest.fixture
def repository() -> NotificationRepository:
    return NotificationRepository()


@pytest.mark.parametrize(
    ("policy_number", "expected"),
    [
        ("MOT-4471", None),
        ("mot-4471", "POLICY_NOT_FOUND"),
        ("UNKNOWN", "POLICY_NOT_FOUND"),
    ],
    ids=[
        "policy_in_the_master_is_found",
        "case_mismatch_is_not_found",
        "absent_policy_is_not_found",
    ],
)
def test_v1_requires_the_policy_to_exist_in_the_master(
    policy_client: StubPolicyClient, policy_number: str, expected: str | None
) -> None:
    """WI-0142 AC-4. Match is exact string equality, including case."""
    notification = a_notification(policy_number=policy_number)
    failure = evaluate_policy_exists(notification, policy_client)
    assert (failure.code if failure else None) == expected


@pytest.mark.parametrize(
    ("loss_date", "expected"),
    [
        (date(2026, 3, 14), "LOSS_BEFORE_INCEPTION"),
        (date(2026, 3, 15), None),
        (date(2026, 3, 16), None),
    ],
    ids=[
        "day_before_inception_is_not_covered",
        "inception_date_itself_is_covered",
        "day_after_inception_is_covered",
    ],
)
def test_v2_attaches_cover_on_the_inception_date(
    motor_policy: Policy, loss_date: date, expected: str | None
) -> None:
    """WI-0142 AC-1, AC-2, AC-3. Cover attaches on the effective date."""
    notification = a_notification(loss_date=loss_date)
    failure = evaluate_loss_after_inception(notification, motor_policy)
    assert (failure.code if failure else None) == expected


@pytest.mark.parametrize(
    ("cancellation_date", "loss_date", "expected"),
    [
        (date(2026, 6, 1), date(2026, 5, 31), None),
        (date(2026, 6, 1), date(2026, 6, 1), "POLICY_CANCELLED"),
        (date(2026, 6, 1), date(2026, 6, 2), "POLICY_CANCELLED"),
        (None, date(2026, 6, 1), None),
    ],
    ids=[
        "day_before_cancellation_is_covered",
        "cancellation_date_itself_is_not_covered",
        "after_cancellation_is_not_covered",
        "uncancelled_policy_is_unaffected",
    ],
)
def test_v7_ends_cover_at_the_cancellation_date(
    motor_policy: Policy,
    cancellation_date: date | None,
    loss_date: date,
    expected: str | None,
) -> None:
    """WI-0158 AC-1, AC-2, AC-3. Cancellation takes effect at the start
    of the cancellation date, so a loss on that date is not covered."""
    policy = motor_policy.model_copy(update={"cancellation_date": cancellation_date})
    notification = a_notification(loss_date=loss_date)
    failure = evaluate_policy_not_cancelled(notification, policy)
    assert (failure.code if failure else None) == expected


@pytest.mark.parametrize(
    ("loss_date", "expected"),
    [
        (date(2027, 3, 13), None),
        (date(2027, 3, 14), None),
        (date(2027, 3, 15), "LOSS_AFTER_EXPIRY"),
    ],
    ids=[
        "day_before_expiry_is_covered",
        "expiry_date_itself_is_covered",
        "day_after_expiry_is_not_covered",
    ],
)
def test_v3_ends_cover_after_the_expiry_date(
    motor_policy: Policy, loss_date: date, expected: str | None
) -> None:
    """A loss on the expiry date is covered. The day after is not."""
    notification = a_notification(loss_date=loss_date)
    failure = evaluate_loss_before_expiry(notification, motor_policy)
    assert (failure.code if failure else None) == expected


@pytest.mark.parametrize(
    ("estimated_amount", "expected"),
    [
        (Decimal("54999.99"), None),
        (Decimal("55000.00"), None),
        (Decimal("55000.01"), "AMOUNT_EXCEEDS_LIMIT"),
    ],
    ids=[
        "amount_below_the_limit_is_within_cover",
        "amount_equal_to_the_limit_is_within_cover",
        "amount_above_the_limit_is_not_covered",
    ],
)
def test_v4_accepts_an_amount_equal_to_the_limit(
    motor_policy: Policy, estimated_amount: Decimal, expected: str | None
) -> None:
    """An amount equal to the limit is within cover."""
    notification = a_notification(estimated_amount=estimated_amount)
    failure = evaluate_amount_within_limit(notification, motor_policy)
    assert (failure.code if failure else None) == expected


@pytest.mark.parametrize(
    ("claim_type", "expected"),
    [
        ("collision", "TYPE_NOT_COVERED"),
        ("theft", None),
        ("glass", None),
        ("liability", None),
        ("weather", None),
    ],
    ids=[
        "type_not_on_the_product_is_refused",
        "theft_is_permitted",
        "glass_is_permitted",
        "liability_is_permitted",
        "weather_is_permitted",
    ],
)
def test_v5_rejects_types_not_permitted_on_the_product(
    motor_policy: Policy, claim_type: ClaimType, expected: str | None
) -> None:
    """V-5 compares a vocabulary value against the product's permitted types."""
    policy = motor_policy.model_copy(
        update={"permitted_claim_types": ("theft", "glass", "weather", "liability")}
    )
    notification = a_notification(claim_type=claim_type)
    failure = evaluate_claim_type_covered(notification, policy)
    assert (failure.code if failure else None) == expected


@pytest.mark.parametrize(
    ("record_first", "policy_number", "loss_date", "claim_type", "expected"),
    [
        (True, "MOT-4479", date(2026, 6, 1), "collision", "DUPLICATE_NOTIFICATION"),
        (True, "MOT-4471", date(2026, 6, 1), "collision", None),
        (True, "MOT-4479", date(2026, 6, 2), "collision", None),
        (True, "MOT-4479", date(2026, 6, 1), "theft", None),
        (False, "MOT-4479", date(2026, 6, 1), "collision", None),
    ],
    ids=[
        "matching_recorded_notification_is_duplicate",
        "different_policy_is_not_duplicate",
        "different_loss_date_is_not_duplicate",
        "different_claim_type_is_not_duplicate",
        "refused_submission_is_not_duplicate",
    ],
)
def test_v6_rejects_a_matching_recorded_notification(
    repository: NotificationRepository,
    record_first: bool,
    policy_number: str,
    loss_date: date,
    claim_type: ClaimType,
    expected: str | None,
) -> None:
    """WI-0151 AC-1, AC-2, AC-3. Only a recorded notification can be duplicated."""
    original = a_notification(
        policy_number="MOT-4479",
        loss_date=date(2026, 6, 1),
        claim_type="collision",
    )
    if record_first:
        repository.record(
            ClaimRecord(
                claim_reference=repository.issue_claim_reference(),
                policy_number=original.policy_number,
                loss_date=original.loss_date,
                claim_type=original.claim_type,
                estimated_amount=original.estimated_amount,
                description=original.description,
            )
        )
    notification = a_notification(
        policy_number=policy_number,
        loss_date=loss_date,
        claim_type=claim_type,
    )
    failure = evaluate_not_duplicate(notification, repository)
    assert (failure.code if failure else None) == expected


def test_v1_short_circuits_so_inception_is_not_evaluated(
    policy_client: StubPolicyClient, repository: NotificationRepository
) -> None:
    """WI-0142 AC-4. A missing policy is not evaluated against inception."""
    notification = a_notification(
        policy_number="UNKNOWN",
        loss_date=date(2020, 1, 1),
    )
    failure = evaluate_notification(notification, policy_client, repository)
    assert (failure.code if failure else None) == "POLICY_NOT_FOUND"


def test_v7_is_reported_ahead_of_expiry_on_a_cancelled_policy(
    policy_client: StubPolicyClient, repository: NotificationRepository
) -> None:
    """WI-0158 AC-4. Where a policy is cancelled and the loss also falls
    outside the original term, the handler is told the policy was cancelled."""
    notification = a_notification(
        policy_number="MOT-4500",
        loss_date=date(2026, 1, 8),
        claim_type="collision",
        estimated_amount=Decimal("6000.00"),
    )
    failure = evaluate_notification(notification, policy_client, repository)
    assert (failure.code if failure else None) == "POLICY_CANCELLED"
