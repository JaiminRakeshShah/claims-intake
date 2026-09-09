# Claims Intake Service

The claims portal posts a first notice of loss here. The service looks the
policy up in the policy master, walks the rule table in
`docs/api-contract.md`, and either records the notification and returns a
claim reference or refuses with a specific reason. It does not decide
whether a claim will be paid.

## Where things are

| Path | What it holds |
| --- | --- |
| `docs/api-contract.md` | What the service accepts, returns, and refuses. The authority. |
| `docs/requirements-brief.md` | The open work items and their acceptance criteria. |
| `docs/payload-triage.md` | Day 1 classification of the edge payloads. |
| `data/` | Synthetic policies and notification payloads. |
| `src/claims/` | The service. |
| `tests/` | Unit tests mirror `src/claims/`. Integration tests exercise HTTP. |

## Working in this repository

You are already inside a Linux container. Confirm it before you start:

```
uname -sm     # Linux aarch64
pwd           # /workspaces/claims-intake
```

Dependencies are installed when the container is created. There is no install
step. If a tool you need is missing, that is a defect in the image
specification and should be reported rather than worked around.

## Run the service

```
uv run uvicorn claims.api.routes:app --host 0.0.0.0 --port 8000
```

Leave that process running. In another terminal, a valid notice:

```
curl -sS -X POST http://127.0.0.1:8000/notifications \
  -H 'Content-Type: application/json' \
  -d '{"policy_number":"MOT-4471","loss_date":"2026-04-02","claim_type":"collision","estimated_amount":"4200.00","description":"Rear ended at a junction."}'
```

A recorded notice returns `201` and a `claim_reference`. The contract in
`docs/api-contract.md` is the list of refusals.

## Run the tests

```
uv run pytest
uv run ruff check .
uv run mypy
```

## Image platform

This container is aarch64. The hosts that will run the image are not: they
are linux/amd64. Docker builds for the machine it is standing on unless it
is told otherwise, so a default build here produces an ARM image. That
image starts on this lab box and is useless on the deployment servers,
which cannot execute ARM userland.

The platform argument names the CPU the image is *for*, separately from the
CPU we are *on*. That is why the build below does not follow the
architecture `uname` just printed.

```
docker buildx build --platform linux/amd64 -t claims-intake:0.1.0 --load .
docker run --rm -p 8000:8000 claims-intake:0.1.0
```

The same `POST /notifications` as above reaches the process on port 8000.

## Data

Everything in `data/` is synthetic and was authored for this program. It
contains no real client data and no named clients.
