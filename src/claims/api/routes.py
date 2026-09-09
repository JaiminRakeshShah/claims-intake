"""HTTP surface for the claims intake service.

This layer does three things and no more: it parses the request, it calls the
service, and it maps the outcome to a status code. It holds no rule logic. A rule
that appears here is a rule the service layer cannot be tested for.

Day 4 lab. Implement against `docs/api-contract.md` sections 5 and 6.
"""

from __future__ import annotations

from fastapi import FastAPI

from claims.policy_client import PolicyClient, StubPolicyClient
from claims.repository import NotificationRepository


def create_app(
    policy_client: PolicyClient | None = None,
    repository: NotificationRepository | None = None,
) -> FastAPI:
    """Build an app with injected dependencies. The route is Day 4 work."""
    application = FastAPI(title="Claims Intake Service")
    application.state.policy_client = policy_client or StubPolicyClient()
    application.state.repository = repository or NotificationRepository()
    return application


app = create_app()
