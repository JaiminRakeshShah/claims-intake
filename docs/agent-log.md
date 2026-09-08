# Agent log

Two decisions from writing `src/claims/service.py`. One we kept. One we threw out.
Each reason is a contract line, an acceptance criterion, or a failure that would
have happened if we had chosen the other way.

## 1. `evaluate_notification` does not take the policy client

**Change.** The starter’s `evaluate_notification` took a notification, a policy
client, and a repository, and it was supposed to run every rule. The agent’s
version takes a notification and a policy and returns `RuleFailure | None`.

**Decision.** Keep that shape. V-1 stays in `submit_notification`, which is the
function that actually calls the client. `evaluate_notification` only walks
V-2, V-7, V-3, V-4, V-5.

**Reason.** Contract section 1 says a policy the master cannot read is a
different condition from a policy that does not exist. Section 6 maps them to
different codes and statuses: no match is `POLICY_NOT_FOUND` / 422; timeout,
unreachable, and unparsable are 5xx, with `reason` intact for the HTTP layer.
A function that holds the client can only “handle” V-1 by catching. If that
catch is broader than `PolicyNotFound` — and a version that still took the
client would be the natural place to put one — `submit_notification` reports
that a policy does not exist when it does not know. That is the failure the
dependency-boundary criterion names. WI-0142 AC-4 still holds: V-1 short
circuits in `submit_notification` before any policy-field rule runs.

The V-2 through V-5 tests would not have caught this. They call the individual
rule functions with a `Policy` already in hand. A reviewer who only looked at
those green tests would have kept the starter signature.

## 2. Keeping V-6 out of the table

**Change.** Where the duplicate check runs.

**Decision.** `POLICY_RULES` is only V-2, V-7, V-3, V-4, V-5.
`submit_notification` calls `evaluate_not_duplicate` after that.

**Reason.** Contract section 4.1 puts V-6 last. WI-0151 AC-1 is a lookup of
what was recorded, not a field on a policy. The C3 rule for
`evaluate_notification` is that it takes a notification and a policy and does
no I/O. Putting `find_matching` in `POLICY_RULES` by closing over the
repository would still have left V-6 last, so a reviewer checking only 4.1
would have signed off. Then `evaluate_notification` would talk to storage, and
the no-I/O rule would be false.