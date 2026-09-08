# Pipeline gate observation

Observed 2026-09-08 against `JaiminRakeshShah/claims-intake`.

## What the job does

`.github/workflows/checks.yaml` runs on pull requests. It installs with `uv sync --frozen` so the lockfile is used as-is and is not re-resolved. It then runs ruff, mypy over `src` and `tests`, and pytest. None of those steps set `continue-on-error`, and none of the commands swallow a non-zero exit (`|| true` or equivalent). Any of them failing fails the job.

Third-party actions are pinned to commit SHAs (`actions/checkout` v7.0.1, `astral-sh/setup-uv` v10.0.1).

## Real failure

The same ruff command the job will run was executed against this tree:

```
.venv/bin/ruff check .
```

It exited 1:

- `TRY004` at `src/claims/models.py:59` (`ValueError` raised for an invalid type)
- `DTZ001` at `tests/unit/test_models.py:129` (`datetime(...)` with no `tzinfo`)

A pull request of this tree would therefore fail the Ruff step, and the job would be red. Pytest on the same tree: 104 passed.

That is the gate working as a signal: a broken check is visible.

Those two findings were then corrected so the same command exits 0: the validator rejects a `datetime` with `PydanticCustomError` (TRY004), and the test constructs an aware `datetime` with `datetime.UTC` (DTZ001 / UP017).

## Protection is not configured

GitHub reports `main` as `protected: false`. The repository has no rulesets. Without a branch protection rule or ruleset that requires the `checks` job to pass, GitHub will still allow the pull request to merge.

The workflow can fail. It cannot, by itself, stop a merge. Until protection is configured to require this job, the gate is advisory.
