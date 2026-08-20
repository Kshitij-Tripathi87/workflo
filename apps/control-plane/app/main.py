"""Tenant Shield Control Plane — FastAPI application factory."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.health import router as health_router
from app.api.v1.runs import router as runs_router
from app.api.v1.keys import router as keys_router
from app.api.v1.artifacts import router as artifacts_router
from app.api.v1.auth import router as auth_router
from app.api.v1.key_provisioning import router as key_provisioning_router
from app.api.oauth import router as oauth_router
from app.db.database import init_db, get_db
from app.db.queue import run_queue
from app.db.models import DeviceCode
from app.core.config import settings
from app.core.crypto import utc_now
from app.core.security import verify_bearer_token


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables (dev mode) + connect queue
    await init_db()
    if settings.redis_url:
        run_queue.connect_redis(settings.redis_url)
    yield
    # Shutdown: cleanup (Redis connection close, etc.)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Tenant Shield Control Plane",
        version="0.2.0",
        description="The orchestration API for the Tenant Shield multi-tenant testing platform.",
        lifespan=lifespan,
    )
    app.include_router(health_router, prefix="/v1", tags=["health"])
    app.include_router(runs_router, prefix="/v1", tags=["runs"])
    app.include_router(keys_router, prefix="/v1", tags=["keys"])
    app.include_router(artifacts_router, prefix="/v1", tags=["artifacts"])
    app.include_router(auth_router, prefix="/v1", tags=["auth"])
    app.include_router(key_provisioning_router, prefix="/v1", tags=["key-provisioning"])
    # Standard OAuth endpoints (RFC 8628/6749/7009) at root level for
    # cortex-auth client compatibility.
    app.include_router(oauth_router)

    @app.get("/")
    async def root():
        return {"service": "tenant-shield-control-plane", "version": "0.2.0", "docs": "/docs"}

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request, next: str = ""):
        """Server-rendered login page. Stores the access token in
        sessionStorage and redirects to ``next`` on success."""
        return HTMLResponse(content=AUTH_PAGE_HTML.format(
            page_title="Sign in",
            action="/v1/auth/login",
            button_label="Sign in",
            mode="login",
            next_url=_html_escape(next),
            alt_link='/signup',
            alt_label="Don't have an account? Sign up",
        ))

    @app.get("/signup", response_class=HTMLResponse)
    async def signup_page(request: Request, next: str = ""):
        """Server-rendered signup page."""
        return HTMLResponse(content=AUTH_PAGE_HTML.format(
            page_title="Create account",
            action="/v1/auth/signup",
            button_label="Create account",
            mode="signup",
            next_url=_html_escape(next),
            alt_link='/login',
            alt_label="Already have an account? Sign in",
        ))

    # Device authorization page (RFC 8628). Requires an authenticated
    # browser session: the page JS checks sessionStorage for the access
    # token and redirects to /login if absent; POST /device rejects the
    # submission without a valid Bearer token.
    @app.get("/device", response_class=HTMLResponse)
    async def device_authorization_page(request: Request, user_code: str = ""):
        """Show the device authorization page for user approval."""
        return HTMLResponse(content=DEVICE_AUTH_HTML.format(
            user_code=_html_escape(user_code),
            client_name="workflo CLI",
            scopes="workflo:runs:create workflo:runs:read workflo:receipts:read workflo:projects:read",
        ))

    @app.post("/device", response_class=HTMLResponse)
    async def device_authorization_submit(
        request: Request,
        user_code: str = Form(...),
        action: str = Form(...),
        access_token: str = Form(""),
        db: AsyncSession = Depends(get_db),
    ):
        """Process the user's authorization decision.

        Identity binding: the submission must carry a valid Bearer access
        token (the authenticated browser session). The approving user is
        bound to the device code so the subsequent token grant issues
        tokens for the REAL user, never a demo placeholder.
        """
        try:
            _, user = await verify_bearer_token(f"Bearer {access_token}", db)
        except HTTPException:
            return HTMLResponse(content=DEVICE_AUTH_RESULT_HTML.format(
                title="Sign in required",
                h1_class="error",
                h1_text="Sign in required",
                message="You must be signed in to authorize a device. Return to the login page and sign in first.",
            ))

        stmt = select(DeviceCode).where(DeviceCode.user_code == user_code)
        result = await db.execute(stmt)
        dc = result.scalar_one_or_none()

        if not dc:
            return HTMLResponse(content=DEVICE_AUTH_RESULT_HTML.format(
                title="Error",
                h1_class="error",
                h1_text="Error",
                message="Invalid user code. The code may have expired or been entered incorrectly.",
            ))

        if utc_now() > dc.expires_at:
            return HTMLResponse(content=DEVICE_AUTH_RESULT_HTML.format(
                title="Error",
                h1_class="error",
                h1_text="Error",
                message="This user code has expired. Please start the login process again.",
            ))

        if dc.authorized_at:
            return HTMLResponse(content=DEVICE_AUTH_RESULT_HTML.format(
                title="Error",
                h1_class="error",
                h1_text="Error",
                message="This code has already been used.",
            ))

        if action == "allow":
            dc.user_id = user.id
            dc.authorized_at = utc_now()
            await db.commit()
            return HTMLResponse(content=DEVICE_AUTH_RESULT_HTML.format(
                title="Authorized",
                h1_class="success",
                h1_text="Authorized",
                message="Authorization successful! You can close this window and return to the CLI.",
            ))
        else:
            await db.delete(dc)
            await db.commit()
            return HTMLResponse(content=DEVICE_AUTH_RESULT_HTML.format(
                title="Error",
                h1_class="error",
                h1_text="Error",
                message="Authorization denied.",
            ))

    return app


def _html_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# HTML templates for device authorization
DEVICE_AUTH_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Authorize Device - Cortex</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 2rem 1rem; color: #1a1a1a; background: #fafafa; line-height: 1.6; }}
        .card {{ background: white; border: 1px solid #e5e5e5; border-radius: 8px; padding: 2rem; }}
        h1 {{ font-size: 1.5rem; font-weight: 600; margin: 0 0 0.5rem; color: #000; }}
        .subtitle {{ color: #666; margin-bottom: 1.5rem; }}
        .code-display {{ font-family: 'SF Mono', Monaco, monospace; font-size: 2rem; letter-spacing: 0.2em; text-align: center; padding: 1rem; background: #f5f5f5; border-radius: 6px; margin: 1rem 0; color: #000; }}
        .info {{ font-size: 0.875rem; color: #666; margin: 1rem 0; }}
        .info strong {{ color: #333; }}
        .btn-group {{ display: flex; gap: 0.75rem; margin-top: 1.5rem; }}
        button {{ flex: 1; padding: 0.75rem 1rem; font-size: 1rem; font-weight: 500; border-radius: 6px; border: 1px solid transparent; cursor: pointer; transition: background 0.15s, border-color 0.15s; }}
        .btn-allow {{ background: #000; color: white; }}
        .btn-allow:hover {{ background: #333; }}
        .btn-deny {{ background: white; color: #333; border-color: #ddd; }}
        .btn-deny:hover {{ background: #f5f5f5; border-color: #ccc; }}
        .footer {{ margin-top: 2rem; font-size: 0.75rem; color: #999; text-align: center; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>Authorize Device</h1>
        <p class="subtitle">A device is requesting access to your Cortex account.</p>
        <div class="code-display">{user_code}</div>
        <p class="info"><strong>Client:</strong> {client_name}</p>
        <p class="info"><strong>Requested scopes:</strong> {scopes}</p>
        <form method="post" id="approval-form">
            <input type="hidden" name="user_code" value="{user_code}">
            <input type="hidden" name="access_token" id="access-token" value="">
            <div class="btn-group">
                <button type="submit" name="action" value="allow" class="btn-allow">Allow</button>
                <button type="submit" name="action" value="deny" class="btn-deny">Deny</button>
            </div>
        </form>
        <p class="footer">Cortex — cortex.dev</p>
    </div>
    <script>
        // Identity binding: the approving action must carry the signed-in
        // user's access token. If none is stored, send the user to /login
        // first (the token is kept in sessionStorage for the tab).
        (function () {{
            var token = sessionStorage.getItem("cortex_access_token");
            if (!token) {{
                window.location.href = "/login?next=" + encodeURIComponent(window.location.pathname + window.location.search);
                return;
            }}
            document.getElementById("access-token").value = token;
        }})();
    </script>
</body>
</html>
"""

AUTH_PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{page_title} - Cortex</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 400px; margin: 0 auto; padding: 3rem 1rem; color: #1a1a1a; background: #fafafa; line-height: 1.6; }}
        .card {{ background: white; border: 1px solid #e5e5e5; border-radius: 8px; padding: 2rem; }}
        h1 {{ font-size: 1.5rem; font-weight: 600; margin: 0 0 1.5rem; color: #000; }}
        label {{ display: block; font-size: 0.875rem; font-weight: 500; margin: 1rem 0 0.25rem; color: #333; }}
        input {{ width: 100%; padding: 0.6rem 0.75rem; font-size: 1rem; border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box; }}
        button {{ width: 100%; margin-top: 1.5rem; padding: 0.75rem 1rem; font-size: 1rem; font-weight: 500; background: #000; color: white; border: none; border-radius: 6px; cursor: pointer; }}
        button:hover {{ background: #333; }}
        .error {{ color: #c00; font-size: 0.875rem; margin-top: 0.75rem; }}
        .alt {{ display: block; text-align: center; margin-top: 1.5rem; font-size: 0.875rem; color: #666; }}
        .alt a {{ color: #000; }}
        .footer {{ margin-top: 2rem; font-size: 0.75rem; color: #999; text-align: center; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>{page_title}</h1>
        <form id="auth-form">
            <label for="email">Email</label>
            <input type="email" id="email" name="email" required autocomplete="email">
            <label for="password">Password</label>
            <input type="password" id="password" name="password" required autocomplete="current-password">
            <button type="submit">{button_label}</button>
        </form>
        <div class="error" id="error" hidden></div>
        <span class="alt"><a href="{alt_link}">{alt_label}</a></span>
        <p class="footer">Cortex — cortex.dev</p>
    </div>
    <script>
        (function () {{
            var form = document.getElementById("auth-form");
            var errorBox = document.getElementById("error");
            var nextUrl = "{next_url}" || "/";
            form.addEventListener("submit", function (ev) {{
                ev.preventDefault();
                errorBox.hidden = true;
                var email = document.getElementById("email").value;
                var password = document.getElementById("password").value;
                var body = new URLSearchParams();
                body.set("email", email);
                body.set("password", password);
                fetch(form.getAttribute("data-action") || "{action}", {{
                    method: "POST",
                    headers: {{ "Content-Type": "application/x-www-form-urlencoded" }},
                    body: body.toString(),
                }}).then(function (resp) {{
                    return resp.json().then(function (data) {{
                        if (!resp.ok) {{
                            throw new Error((data && data.detail) || ("Request failed: " + resp.status));
                        }}
                        return data;
                    }});
                }}).then(function (data) {{
                    if (data.access_token) {{
                        sessionStorage.setItem("cortex_access_token", data.access_token);
                        window.location.href = nextUrl;
                    }} else {{
                        errorBox.textContent = "Signed in, but no access token returned.";
                        errorBox.hidden = false;
                    }}
                }}).catch(function (err) {{
                    errorBox.textContent = err.message;
                    errorBox.hidden = false;
                }});
            }});
        }})();
    </script>
</body>
</html>
"""

DEVICE_AUTH_RESULT_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Cortex</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 2rem 1rem; color: #1a1a1a; background: #fafafa; line-height: 1.6; }}
        .card {{ background: white; border: 1px solid #e5e5e5; border-radius: 8px; padding: 2rem; text-align: center; }}
        .success {{ color: #0a7f0a; }}
        .error {{ color: #c00; }}
        h1 {{ font-size: 1.5rem; font-weight: 600; margin: 0 0 1rem; }}
        p {{ color: #666; }}
        .footer {{ margin-top: 2rem; font-size: 0.75rem; color: #999; }}
    </style>
</head>
<body>
    <div class="card">
        <h1 class="{h1_class}">{h1_text}</h1>
        <p>{message}</p>
        <p class="footer">Cortex — cortex.dev</p>
    </div>
</body>
</html>
"""


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
