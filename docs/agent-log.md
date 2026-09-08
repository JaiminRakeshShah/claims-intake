# Agent log

Decisions we made while writing `src/claims/service.py`. Each one names what we changed, what we kept, and what we threw out.

## 1. Putting `ok()` back

**Change.** How a rule says it passed.

**Decision.** Every rule still returns `ValidationOutcome.ok()` or `.failed()`. V-1 is its own function again.

**Reason.** That is the pattern the starter already wrote for `evaluate_policy_exists`.

**Rejected.** The agent rewrote the file so a passing rule returned `None`, and it folded V-1 into `submit_notification`. Pytest still passed. `failure.code if failure else None` works on both shapes, so a reviewer who only looked at the green tests would have kept it. We did not. We changed `service.py` after the agent was already done, because dropping `ok()` meant V-1 no longer looked like the method the course shipped.

## 2. Keeping V-6 out of the table

**Change.** Where the duplicate check runs.

**Decision.** `POLICY_RULES` is only V-2, V-7, V-3, V-4, V-5. `submit_notification` calls `evaluate_not_duplicate` after that.

**Reason.** Contract section 4.1 puts V-6 last. WI-0151 AC-1 is a lookup of what was recorded, not a field on a policy.

**Rejected.** Put `find_matching` in `POLICY_RULES` by closing over the repository. The order would still have been last, so a reviewer checking only 4.1 would have signed off. Then `evaluate_notification` would talk to storage. The brief said it takes a notification and a policy and does no I/O.
