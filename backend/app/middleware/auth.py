"""FastAPI auth middleware/dependencies.

Provides:
- `get_current_user`: Dependency that verifies the bearer token.
- `require_role(role)`: Dependency factory that requires a specific role.
- `AuthMiddleware`: Optional middleware for async enforcement (kept simple in v1).
"""

from fastapi import Depends, Request
from typing import Optional

from app.core.auth import User, verify_token, extract_bearer_token
from app.core.settings import settings
from app.core.exceptions import CortexAuthError, CortexForbiddenError


# Routes that never require auth
PUBLIC_PATHS = {"/health", "/version", "/metrics", "/api/v1/health"}


async def get_current_user(request: Request) -> User:
    """
    FastAPI dependency: returns the authenticated user.

    Auth is bypassed when AUTH_REQUIRED=false (dev mode).
    """
    if not settings.AUTH_REQUIRED:
        return User(
            subject="dev-user",
            email="dev@example.com",
            name="Dev User",
            roles=["admin"],
        )

    auth_header = request.headers.get("Authorization")
    token = extract_bearer_token(auth_header)
    return await verify_token(token)


def require_role(required_role: str):
    """Dependency factory: requires the user to have the given role."""
    async def _check(user: User = Depends(get_current_user)):
        if not user.has_role(required_role):  # type: ignore[arg-type]
            raise CortexForbiddenError(
                f"Role '{required_role}' required for this action"
            )
        return user
    return _check


def is_public_path(path: str) -> bool:
    """Check if a path is exempt from auth."""
    return path in PUBLIC_PATHS or path.startswith("/api/v1/health")
