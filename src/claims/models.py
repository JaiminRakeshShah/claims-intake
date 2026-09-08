"""Boundary models for the claims intake service.

Everything that enters the service is parsed into one of these before any rule
runs. A payload that reaches the rule layer has already been proven well formed,
which is what keeps a shape problem and a content problem from arriving at the
caller as the same status code.

Day 2 assignment. Implement these against `docs/api-contract.md` sections 2 and 3.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

ClaimType = Literal["collision", "theft", "glass", "liability", "weather"]
_CALENDAR_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _require_two_decimal_places(value: Decimal) -> Decimal:
    """Scale is part of the money field, not a display choice."""
    exponent = value.as_tuple().exponent
    if exponent != -2:
        raise ValueError("Expected two decimal places")
    return value


class NotificationRequest(BaseModel):
    """A first notice of loss as submitted by the claims portal.

    Fields and their constraints are specified in contract section 2.2. The model
    is responsible for the shape of the request and for nothing else. Whether the
    policy exists, whether the loss falls inside the term, and whether the amount
    is within the limit are rules, and rules live in `service.py`.

    `policy_number` is declared so that the V-1 rule in `service.py` has something
    to read. Every other field, and every constraint on every field including this
    one, is Day 2's work.
    """

    model_config = ConfigDict(extra="forbid")

    policy_number: str = Field(min_length=1)
    loss_date: date
    claim_type: ClaimType
    estimated_amount: Decimal = Field(gt=0)
    description: str | None = None

    @field_validator("loss_date", mode="before")
    @classmethod
    def loss_date_is_a_calendar_date(cls, value: object) -> object:
        # Section 2.2: calendar date, YYYY-MM-DD.
        if isinstance(value, datetime):
            raise PydanticCustomError(
                "date_type",
                "loss_date is a calendar date, not a datetime",
            )
        if isinstance(value, str) and _CALENDAR_DATE.fullmatch(value) is None:
            raise ValueError("loss_date must be YYYY-MM-DD")
        return value

    @field_validator("estimated_amount")
    @classmethod
    def estimated_amount_is_exact_cents(cls, value: Decimal) -> Decimal:
        return _require_two_decimal_places(value)


class Policy(BaseModel):
    """A policy as this service works with it.

    Built from the `PolicyRecord` the policy client returns. The fields the rules
    compare against are the reason this model exists.

    `cancellation_date` is `date | None` with no default so a comparison against
    it without first handling absence fails type checking (WI-0158 AC-3).
    """

    model_config = ConfigDict(extra="forbid")

    policy_number: str = Field(min_length=1)
    product: str
    effective_date: date
    expiry_date: date
    cancellation_date: date | None
    limit: Decimal = Field(gt=0)
    permitted_claim_types: tuple[ClaimType, ...]

    @field_validator("limit")
    @classmethod
    def limit_is_exact_cents(cls, value: Decimal) -> Decimal:
        return _require_two_decimal_places(value)


@dataclass(frozen=True)
class RuleFailure:
    """A failed rule, with the two identifiers kept as separate fields.

    `rule` is the table id (`V-2`). `code` is the caller-visible contract code
    (`LOSS_BEFORE_INCEPTION`). They are distinct so a rule id cannot be passed
    where a code is expected.

    `detail` carries the values the rule compared, as contract section 5 names
    them. The HTTP layer maps `code` to a status; it does not invent these keys.
    """

    rule: str
    code: str
    detail: dict[str, Any] = field(default_factory=dict)


class ClaimRecord(BaseModel):
    """A claim record: a notification that passed every rule and was written.

    Named for the record the handler quotes, not for the request that produced
    it. A payload that failed the model never becomes a `ClaimRecord`, so the
    repository has nothing it can persist for a rejection (WI-0151 AC-3).

    Carries the claim reference issued at the time it was recorded. Contract
    section 3 fixes the reference format.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_reference: str = Field(pattern=r"^CLM-\d{4}-\d{6}$")
    policy_number: str = Field(min_length=1)
    loss_date: date
    claim_type: ClaimType
    estimated_amount: Decimal = Field(gt=0)
    description: str | None = None

    @field_validator("estimated_amount")
    @classmethod
    def estimated_amount_is_exact_cents(cls, value: Decimal) -> Decimal:
        return _require_two_decimal_places(value)