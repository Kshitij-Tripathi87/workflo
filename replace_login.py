import re

with open(r'C:\Users\21330\Documents\workflowpro-tests\apps\control-plane\app\api\v1\auth.py', 'r') as f:
    content = f.read()

# Replace the login function
old_login = """@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    # FastAPI dependency for client host — injected as kwarg
    client_host: str = Depends(lambda request: request.client.host if request.client else "127.0.0.1"),
):
    """Authenticate a user and issue OAuth tokens.

    Rate-limited: 5 attempts per IP per 5 minutes.
    On success returns tokens + user info; on failure returns
    ``authorization_pending`` with a generic message (no email enum).
    """
    # Rate limit check
    if not _check_login_rate_limit(client_host):
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Try again in 5 minutes.",
        )

    # Find user by email
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.password_hash):
        # Generic failure — don't enumerate whether email or password is wrong
        raise HTTPException(
            status_code=400,
            detail="Invalid credentials",
        )

    # Find or create demo project
    project = await get_or_create_demo_project(db)

    # Get or create demo user ID (in production, from the authenticated session)
    # Here we use the user's ID since they just logged in
    user_id = user.id

    # Create OAuth tokens
    access_token = generate_access_token()
    refresh_token = generate_refresh_token()

    oauth_token = OAuthToken(
        user_id=user_id,
        client_id="workflo_cli",  # CLI default client
        organization_id=None,
        workspace_id=project.id,
        scopes=["openid", "profile", "offline_access",
                "workflo:runs:create", "workflo:runs:read",
                "workflo:receipts:read", "workflo:projects:read"],
        access_token_hash=hash_token(access_token),
        refresh_token_hash=hash_token(refresh_token),
        access_token_expires_at=token_expiry(ACCESS_TOKEN_EXPIRY_MINUTES),
        refresh_token_expires_at=refresh_token_expiry(REFRESH_TOKEN_EXPIRY_DAYS),
    )
    db.add(oauth_token)
    await db.flush()

    # Link to user
    oauth_token.user_id = user_id
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=ACCESS_TOKEN_EXPIRY_MINUTES * 60,
        refresh_token=refresh_token,)"""

new_login = """@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Authenticate a user and issue OAuth tokens.

    Rate-limited: 5 attempts per IP per 5 minutes.
    On success returns tokens + user info; on failure returns
    a generic ``Invalid credentials`` message (no email enum).
    """
    # Rate limit check (simple in-memory, per-IP)
    client_host = request.client.host if request.client else "127.0.0.1"
    if not _check_login_rate_limit(client_host):
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Try again in 5 minutes.",
        )

    # Find user by email
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.password_hash):
        # Generic failure — don't enumerate whether email or password is wrong
        raise HTTPException(
            status_code=400,
            detail="Invalid credentials",
        )

    # Find or create demo project
    project = await get_or_create_demo_project(db)

    # Create OAuth tokens
    access_token = generate_access_token()
    refresh_token = generate_refresh_token()

    oauth_token = OAuthToken(
        user_id=user.id,
        client_id="workflo_cli",  # CLI default client
        organization_id=None,
        workspace_id=project.id,
        scopes=["openid", "profile", "offline_access",
                "workflo:runs:create", "workflo:runs:read",
                "workflo:receipts:read", "workflo:projects:read"],
        access_token_hash=hash_token(access_token),
        refresh_token_hash=hash_token(refresh_token),
        access_token_expires_at=token_expiry(ACCESS_TOKEN_EXPIRY_MINUTES),
        refresh_token_expires_at=refresh_token_expiry(REFRESH_TOKEN_EXPIRY_DAYS),
    )
    db.add(oauth_token)
    await db.flush()

    return TokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=ACCESS_TOKEN_EXPIRY_MINUTES * 60,
        refresh_token=refresh_token,)"""

if old_login in content:
    content = content.replace(old_login, new_login)
    with open(r'C:\Users\21330\Documents\workflowpro-tests\apps\control-plane\app\api\v1\auth.py', 'w') as f:
        f.write(content)
    print("Replacement successful")
else:
    print("Old login not found")
    # Debug: print lines around 581
    lines = content.split('\n')
    for i in range(578, 600):
        if i < len(lines):
            print(f"{i}: {lines[i]}")