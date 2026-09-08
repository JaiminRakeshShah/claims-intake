# Payload Triage

Every payload in `data/fnol_edge.json` classified against `docs/api-contract.md` as you have completed it. The classification records what the contract says the service does, which is not always what the payload obviously violates.

Fill one row per payload. Where a payload is accepted, leave the rule, code, and status columns as `-`.

## Classification

| Payload | Outcome | Rule | Code | Status |
| --- | --- | --- | --- | --- |
| EDGE-01 | accepted | - | - | - |
| EDGE-02 | accepted | - | - | - |
| EDGE-03 | accepted | - | - | - |
| EDGE-04 | rejected | V-7 | POLICY_CANCELLED | 422 |
| EDGE-05 | rejected | V-2 | LOSS_BEFORE_INCEPTION | 422 |
| EDGE-06 | rejected | V-4 | AMOUNT_EXCEEDS_LIMIT | 422 |
| EDGE-07 | rejected | V-1 | POLICY_NOT_FOUND | 422 |
| EDGE-08 | rejected | - | MALFORMED_REQUEST | 400 |
| EDGE-09 | rejected | V-5 | TYPE_NOT_COVERED | 422 |
| EDGE-10 | rejected | V-7 | POLICY_CANCELLED | 422 |
| EDGE-11 | rejected | - | MALFORMED_REQUEST | 400 |
| EDGE-12 | rejected | - | MALFORMED_REQUEST | 400 |

## Decision log

Three payloads cannot be classified against the contract as it shipped, because the contract left a decision unmade. For each one, record the ambiguity, the decision, its authority, and the alternative you rejected.

A decision recorded here and nowhere else has not been made. Amend `docs/api-contract.md` so that a reader of the contract alone could not arrive at the other reading.

### Decision 1

**Payload.** EDGE-07

**The ambiguity.** Section 2.2 describes `policy_number` as the identifier as held in the policy master, but it does not say whether lookup is case-sensitive. `mot-4471` could be treated as `MOT-4471` and accepted, or treated as a different identifier and refused under `V-1`.

**Decision.** Match is exact string equality, including case. `mot-4471` does not exist in the policy master. The service refuses with `V-1`, `POLICY_NOT_FOUND`, status `422`.

**Authority.** Section 2.2, "Identifier as held in the policy master." Rule `V-1`.

**Rejected alternative.** Case-insensitive match, folding `mot-4471` to `MOT-4471` and accepting the notification. That would record a notification under an identifier the master does not hold. A mistyped key would silently bind to a real policy.

**Contract amended.** Section 4: `policy_number` is matched to the policy master by exact string equality, including case. `mot-4471` and `MOT-4471` are different identifiers.

### Decision 2

**Payload.** EDGE-11

**The ambiguity.** `claim_type` is `flood`, which is not in the section 2.3 vocabulary. The shipped contract could be read as a `400` (the value cannot be interpreted) or as `V-5` / `TYPE_NOT_COVERED` / `422` (the type is not permitted on the product).

**Decision.** A `claim_type` outside the vocabulary cannot be interpreted. The service refuses with `2.4`, `MALFORMED_REQUEST`, status `400`. Rule `V-5` is not reached.

**Authority.** Section 2.3, the vocabulary is fixed by this contract. Section 2.4, a value the contract does not define is the caller's code being wrong, not the caller's data being inadmissible.

**Rejected alternative.** Evaluate `V-5` and return `TYPE_NOT_COVERED`. That would treat `flood` as a claim type this service understands. `V-5` compares a vocabulary value against the product's `permitted_claim_types`. Collapsing a closed-vocabulary defect with a product restriction would send the handler the wrong reason. EDGE-09 is the `V-5` case: `collision` is in the vocabulary and is not permitted on the named perils product.

**Contract amended.** Section 4: `claim_type` must be one of the values listed in section 2.3. A value outside that vocabulary cannot be interpreted. Rule `V-5` is not reached. The refusal is `MALFORMED_REQUEST`, status `400`.

### Decision 3

**Payload.** EDGE-12

**The ambiguity.** Section 2.2 requires `estimated_amount` to have two decimal places. `"3499.999"` could be refused as uninterpretable, or accepted and compared to the policy limit, in which case it would pass `V-4` against a limit of `75000.00`.

**Decision.** Scale is part of the field definition. A value that does not have exactly two decimal places cannot be interpreted. The service refuses with `2.4`, `MALFORMED_REQUEST`, status `400`.

**Authority.** Section 2.2 notes, "two decimal places." Section 2.4, a field carrying a value that is not the type this contract defines.

**Rejected alternative.** Accept the value and compare it to `limit`, or round it to two places. Either would record an amount the field is specified not to carry. Downstream systems that key on cents would not agree on `3499.999` versus `3500.00`.

**Contract amended.** Section 4: `estimated_amount` must carry exactly two decimal places and a positive value. A scale other than two cannot be interpreted as the field this contract defines.

## Day 2 reconciliation agreement

**Date.** 2026-08-25  
**Scope.** Caller-facing refusals produced by `NotificationRequest` in `src/claims/models.py`, checked against `docs/api-contract.md` section 6.  
**Out of scope.** Rule outcomes in section 4.2 (Day 3). HTTP mapping of those codes (Day 4).

### Method

1. Listed every constraint `NotificationRequest` enforces (fields, types, extras, empty values, decimal scale, calendar date).
2. For each constraint, asked: is this a response the service returns to the portal?
3. Looked that condition up in section 6 **using the code name the contract already uses**. If the code and status were already specified, recorded a match. If not, amended the contract rather than inventing a second code in the model or the note.
4. Repeated the exercise for `Policy` and `ClaimRecord` to confirm those rejections are not HTTP responses.

Evidence: `tests/unit/test_models.py` (catalog payloads in `data/fnol_edge.json` and `data/fnol_invalid.json`, plus one constructed case per constraint).

### Inventory: `NotificationRequest` → section 6

| Model refusal | Section 6 code | Status | Already specified? |
| --- | --- | --- | --- |
| Extra field | `MALFORMED_REQUEST` | 400 | Yes. Section 2.4. |
| Required field absent | `MALFORMED_REQUEST` | 400 | Yes. Section 2.4. EDGE-08. |
| Wrong JSON type | `MALFORMED_REQUEST` | 400 | Yes. Section 2.4. |
| `claim_type` outside 2.3, including empty | `MALFORMED_REQUEST` | 400 | Yes. Section 4 and section 6. EDGE-11. |
| `estimated_amount` scale other than two decimal places | `MALFORMED_REQUEST` | 400 | Yes. Section 4 and section 6. EDGE-12. |
| `loss_date` not `YYYY-MM-DD`, including a datetime | `MALFORMED_REQUEST` | 400 | Yes. Section 2.2 and 2.4 (wrong type for a calendar date). No new code. |
| Empty `policy_number` | `MALFORMED_REQUEST` | 400 | **Gap.** Section 2.2 said "not empty"; section 6 did not name it. |
| `estimated_amount` not greater than zero | `MALFORMED_REQUEST` | 400 | **Gap.** Section 2.2 said "greater than zero"; section 6 named scale only. |

No model refusal required a new code or a status other than 400. A shape defect and a rule failure stay distinct: 400 vs 422/409.

### Amendments

Added two binding readings in section 4:

- `policy_number` must be a non-empty string. An empty string cannot be interpreted as the identifier this contract defines.
- `estimated_amount` must be greater than zero. A zero or negative amount cannot be interpreted as the field this contract defines.

Extended the `MALFORMED_REQUEST` row in section 6 so it names empty `policy_number` and an amount that is not greater than zero, alongside unknown `claim_type` and wrong decimal scale.

No new error code. These are the same 400 condition as the rest of section 2.4. The contract's existing name `MALFORMED_REQUEST` is kept; the note does not introduce a synonym.

### Not caller-facing

`Policy` and `ClaimRecord` also reject ill-typed values. Those are not portal responses.

- `Policy` is built from the policy master. An unusable master body is `POLICY_MASTER_UNPARSABLE` / 502, already in section 6.
- `ClaimRecord` is written only after every rule has passed. A malformed reference is an internal defect, not a request refusal.

They do not add rows to section 6.

### Result

Section 6 now lists every code this service can return for a request the models refuse. Residual work is Day 3 (rule codes) and Day 4 (status codes on the wire).