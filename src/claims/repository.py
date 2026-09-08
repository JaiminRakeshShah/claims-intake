"""Persistence for recorded notifications.

An in-memory store is sufficient for Week 1 and is deliberate rather than a
shortcut. The rules do not know where a notification is stored, so replacing this
with a database in a later week is a change to one module.

The duplicate check that `WI-0151` describes is a query against what has been
recorded, which is why it belongs here rather than in the rule table.

Day 2 assignment. Implement against `docs/api-contract.md` section 3.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from claims.models import ClaimRecord, ClaimType


class NotificationRepository:
    """Stores claim records and issues claim references."""

    def __init__(self) -> None:
        self._records: list[ClaimRecord] = []
        self._next_sequence: int = 1

    def issue_claim_reference(self) -> str:
        """Return the next unused reference. Format is contract section 3."""
        year = datetime.now(UTC).year
        sequence = self._next_sequence
        self._next_sequence += 1
        return f"CLM-{year}-{sequence:06d}"

    def record(self, claim: ClaimRecord) -> ClaimRecord:
        """Persist a claim record. The reference is already on the record.

        Accepts `ClaimRecord` and not `NotificationRequest` so a refused
        submission cannot be written: it never became a claim record
        (WI-0151 AC-3). Duplicate detection stays in `find_matching`.
        """
        self._records.append(claim)
        return claim

    def find_matching(
        self,
        policy_number: str,
        loss_date: date,
        claim_type: ClaimType,
    ) -> ClaimRecord | None:
        """Return an existing claim record matching all three values.

        `WI-0151` AC-1 fixes which fields constitute a match. AC-3 is the reason
        this searches recorded claims only: a submission that was refused never
        became a `ClaimRecord`, so there is nothing for a later one to duplicate.
        """
        for recorded in self._records:
            if (
                recorded.policy_number == policy_number
                and recorded.loss_date == loss_date
                and recorded.claim_type == claim_type
            ):
                return recorded
        return None