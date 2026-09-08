# Agent decision log (Day 3)

## 1. Accepted — V-6 evaluated in submit_notification, not in POLICY_RULES

**Change.** `POLICY_RULES` contains only V-2, V-7, V-3, V-4, and V-5, each a function of a notification and a policy. `evaluate_notification` walks that table and returns `RuleFailure | None`. `submit_notification` then calls `evaluate_not_duplicate`, which uses `repository.find_matching`.

**Decision.** Accept this placement.

**Reason.** Contract section 4.1 requires the order V-1, V-2, V-7, V-3, V-4, V-5, V-6. Closing over the repository inside `POLICY_RULES` would still leave V-6 last, so a reviewer checking only 4.1 would have signed off. Then `evaluate_notification` would call `find_matching`, and the C3 rule that it takes a notification and a policy and does no I/O would be false. WI-0151 AC-1 is a lookup of what was recorded, not a field on a policy, which is why that lookup stays in `submit_notification` after the pure table returns.

## 2. Rejected — evaluate_notification taking the policy client and the repository

**Change.** The starter defined `evaluate_notification(notification, policy_client, repository) -> ValidationOutcome`, so the decision function would look up the policy and the store itself.

**Decision.** Reject that signature. Use `evaluate_notification(notification, policy) -> RuleFailure | None`. Catch only `PolicyNotFound` in `evaluate_policy_exists`, as V-1. Do not catch `PolicyLookupFailed` there or in `submit_notification`.

**Reason.** Contract section 6: the master answering with no match is `POLICY_NOT_FOUND` / 422; timeout, unreachable, and unparsable are 504 / 503 / 502. If `evaluate_notification` owned `get_policy` and caught `PolicyLookupFailed` in the same handler as `PolicyNotFound`, `submit_notification` would report that the policy does not exist when the service does not know, and `test_policy_lookup_failure_propagates_with_reason` would fail for all three reasons. WI-0142 AC-4 requires that a missing policy is not evaluated as V-2; that conversion is `except PolicyNotFound` in `evaluate_policy_exists`, at the client boundary, not inside the pure rule table.
