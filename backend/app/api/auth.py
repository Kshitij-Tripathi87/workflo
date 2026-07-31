"""Auth API routes.

Provides:
- GET /auth/me: returns the current authenticated user.
- POST /auth/callback: OIDC callback endpoint (token exchange).
- GET /auth/csrf-token: fetches CSRF token for state-changing requests.
- POST /auth/login: accepts a bearer token and sets an httpOnly cookie.
- POST /auth/logout: clears the httpOnly cookie.
"""

import uuid

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from app.core.auth import User, extract_bearer_token, verify_token
from app.core.settings import settings
from app.middleware.auth import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return {
        "subject": user.subject,
        "email": user.email,
        "name": user.name,
        "roles": user.roles,
    }


@router.get("/callback")
async def auth_callback(code: str, state: str):
    """
    OIDC authorization-code callback.

    Exchanges the code for tokens. In v1 this is a stub that documents the
    expected flow; the frontend handles token acquisition directly via the
    OIDC provider's SDK (e.g. @azure/msal-browser, auth0-react, or keycloak-js).
    """
    return {
        "status": "ok",
        "message": "Frontend should handle token exchange via OIDC SDK",
        "code": code[:8] + "...",
        "state": state[:8] + "...",
    }


@router.get("/csrf-token")
def csrf_token():
    """Return a CSRF token. Callers must present this on state-changing POSTs."""
    return {"csrf_token": str(uuid.uuid4())}


@router.post("/login")
async def login(request: Request):
    """Accept a bearer token and set an httpOnly, Secure, SameSite cookie."""
    token = extract_bearer_token(request.headers.get("Authorization"))
    user = await verify_token(token)

    response = JSONResponse(
        {
            "subject": user.subject,
            "email": user.email,
            "name": user.name,
            "roles": user.roles,
        }
    )
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=not settings.is_dev,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_TTL_MINUTES * 60,
        path="/",
    )
    return response


@router.post("/logout")
def logout():
    """Clear the httpOnly access cookie."""
    response = JSONResponse({"status": "logged_out"})
    response.delete_cookie("access_token", path="/")
    return response
