"""Rule evaluation and notification submission.

This module owns the decision. It does not know it was reached over HTTP, which
is why it can be tested by calling a function with a typed object and asserting on
the result with no server running.

`evaluate_policy_exists` is the pattern every other rule follows: take the
notification and whatever it needs, decide, and return a `ValidationOutcome`.
V-1, V-6, and the policy-field rules are separate functions. `submit_notification`
is the only function that calls all three.

Day 3 assignment. Build the remaining rules test-first against
`docs/api-contract.md` section 4.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from claims.models import ClaimRecord, NotificationRequest, Policy, RuleFailure
from claims.policy_client import PolicyClient, PolicyNotFound, PolicyRecord
from claims.repository import NotificationRepository


@dataclass(frozen=True)
class ValidationOutcome:
    """The result of evaluating one rule, or of submitting a notification.

    `passed` is the only thing a caller has to branch on. When it is false, `rule`
    names the rule that decided it, `code` is the stable contract code, `detail`
    carries the values that produced the decision, and `failure` is the same
    outcome as a `RuleFailure`. When it is true and a notification was recorded,
    `claim_reference` is the reference issued for it.

    There is no status code here. Contract section 6 maps a code to a status, and
    that mapping is applied at the HTTP boundary.
    """

    passed: bool
    rule: str | None = None
    code: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)
    claim_reference: str | None = None
    failure: RuleFailure | None = None

    @classmethod
    def ok(cls) -> ValidationOutcome:
        return cls(passed=True)

    @classmethod
    def accepted(cls, claim_reference: str) -> ValidationOutcome:
        return cls(passed=True, claim_reference=claim_reference)

    @classmethod
    def failed(cls, rule: str, code: str, **detail: Any) -> ValidationOutcome:
        return cls(
            passed=False,
            rule=rule,
            code=code,
            detail=detail,
            failure=RuleFailure(rule=rule, code=code, detail=detail),
        )


def _policy_from_record(record: PolicyRecord) -> Policy:
    """Build the `Policy` the rules compare against from a client `PolicyRecord`."""
    return Policy(
        policy_number=record.policy_number,
        product=record.product,
        effective_date=record.effective_date,
        expiry_date=record.expiry_date,
        cancellation_date=record.cancellation_date,
        limit=record.limit,
        permitted_claim_types=record.permitted_claim_types,
    )


def evaluate_policy_exists(
    notification: NotificationRequest,
    policy_client: PolicyClient,
) -> ValidationOutcome:
    """V-1. The policy must exist in the policy master.

    This rule is different from the others in one way that matters: it is the only
    one that reaches outside the service, so it is the only one that can fail for
    a reason that is not the caller's fault. `PolicyNotFound` is caught here and
    turned into an ordinary refusal, because a policy that does not exist is a
    fact about the caller's data. `PolicyLookupFailed` is deliberately not caught,
    because the caller did nothing wrong and the HTTP layer has to be able to tell
    the two apart. Contract section 6 fixes what each becomes.

    V-1 short circuits. Every other rule compares against a field on a policy, and
    if there is no policy there is nothing to compare against. Reporting
    LOSS_BEFORE_INCEPTION for a policy number that does not exist is not merely
    unhelpful, it is a false statement about the client's data (WI-0142, AC-4).
    """
    try:
        policy_client.get_policy(notification.policy_number)
    except PolicyNotFound:
        return ValidationOutcome.failed(
            "V-1",
            "POLICY_NOT_FOUND",
            policy_number=notification.policy_number,
        )
    return ValidationOutcome.ok()


def evaluate_loss_after_inception(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-2. The loss must not precede policy inception.

    The boundary is stated in contract section 4.2 and in WI-0142 AC-3. A loss on
    the inception date is covered.
    """
    if notification.loss_date < policy.effective_date:
        return ValidationOutcome.failed(
            "V-2",
            "LOSS_BEFORE_INCEPTION",
            loss_date=notification.loss_date,
            effective_date=policy.effective_date,
        )
    return ValidationOutcome.ok()


def evaluate_policy_not_cancelled(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-7. Cover ends at the start of the cancellation date."""
    cancelled = policy.cancellation_date
    if cancelled is not None and notification.loss_date >= cancelled:
        return ValidationOutcome.failed(
            "V-7",
            "POLICY_CANCELLED",
            loss_date=notification.loss_date,
            cancellation_date=cancelled,
        )
    return ValidationOutcome.ok()


def evaluate_loss_before_expiry(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-3. The loss must not fall after the policy expiry date."""
    if notification.loss_date > policy.expiry_date:
        return ValidationOutcome.failed(
            "V-3",
            "LOSS_AFTER_EXPIRY",
            loss_date=notification.loss_date,
            expiry_date=policy.expiry_date,
        )
    return ValidationOutcome.ok()


def evaluate_amount_within_limit(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-4. The estimated amount must not exceed the policy limit.

    An amount equal to the limit is within cover, per contract section 4.2.
    """
    if notification.estimated_amount > policy.limit:
        return ValidationOutcome.failed(
            "V-4",
            "AMOUNT_EXCEEDS_LIMIT",
            estimated_amount=notification.estimated_amount,
            limit=policy.limit,
        )
    return ValidationOutcome.ok()


def evaluate_claim_type_covered(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-5. The claim type must be permitted on the policy's product."""
    if notification.claim_type not in policy.permitted_claim_types:
        return ValidationOutcome.failed(
            "V-5",
            "TYPE_NOT_COVERED",
            claim_type=notification.claim_type,
            permitted_claim_types=policy.permitted_claim_types,
        )
    return ValidationOutcome.ok()


def evaluate_not_duplicate(
    notification: NotificationRequest,
    repository: NotificationRepository,
) -> ValidationOutcome:
    """V-6. A recorded notification with the same three keys is a duplicate."""
    existing = repository.find_matching(
        notification.policy_number,
        notification.loss_date,
        notification.claim_type,
    )
    if existing is not None:
        return ValidationOutcome.failed(
            "V-6",
            "DUPLICATE_NOTIFICATION",
            claim_reference=existing.claim_reference,
        )
    return ValidationOutcome.ok()


# Contract 4.1 among the pure (notification, policy) rules: V-2, V-7, V-3, V-4,
# V-5. V-1 and V-6 are separate methods: V-1 needs the policy client, V-6 needs the
# repository. Putting either lookup in this table would mix deciding with doing.
# submit_notification calls V-1, then this table, then V-6, so 4.1 still holds.
POLICY_RULES: tuple[Callable[[NotificationRequest, Policy], ValidationOutcome], ...] = (
    evaluate_loss_after_inception,
    evaluate_policy_not_cancelled,
    evaluate_loss_before_expiry,
    evaluate_amount_within_limit,
    evaluate_claim_type_covered,
)


def evaluate_notification(
    notification: NotificationRequest,
    policy: Policy,
) -> RuleFailure | None:
    """Evaluate V-2, V-7, V-3, V-4, V-5. No I/O, no writes.

    Order is contract section 4.1 among those rules. First failure wins. V-1 has
    already been answered by having a policy. V-6 is answered after this returns.
    """
    for rule in POLICY_RULES:
        outcome = rule(notification, policy)
        if not outcome.passed:
            return outcome.failure
    return None


def submit_notification(
    notification: NotificationRequest,
    policy_client: PolicyClient,
    repository: NotificationRepository,
) -> ValidationOutcome:
    """V-1, then the policy rules, then V-6, then record if nothing failed.

    Always a `ValidationOutcome`: `passed` says whether it was accepted,
    `claim_reference` is set when it was, and `failure` is set when it was not.

    `PolicyNotFound` is answered by `evaluate_policy_exists`. `PolicyLookupFailed`
    is not caught: it is not a rule outcome, and the HTTP layer maps `reason`.

    Nothing is written before the decision is made.
    """
    missing = evaluate_policy_exists(notification, policy_client)
    if not missing.passed:
        return missing

    policy = _policy_from_record(policy_client.get_policy(notification.policy_number))
    failure = evaluate_notification(notification, policy)
    if failure is not None:
        return ValidationOutcome.failed(failure.rule, failure.code, **failure.detail)

    duplicate = evaluate_not_duplicate(notification, repository)
    if not duplicate.passed:
        return duplicate

    claim = ClaimRecord(
        claim_reference=repository.issue_claim_reference(),
        policy_number=notification.policy_number,
        loss_date=notification.loss_date,
        claim_type=notification.claim_type,
        estimated_amount=notification.estimated_amount,
        description=notification.description,
    )
    recorded = repository.record(claim)
    return ValidationOutcome.accepted(recorded.claim_reference)
