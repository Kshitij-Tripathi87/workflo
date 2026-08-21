"""Live verification of R2 (auth imports), R3 (expired key -> 401 not 500),
R4 (signup after pre-existing demo project/key)."""
import os
import sys
import tempfile

cp = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "control-plane"))
sys.path.insert(0, cp)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "packages", "workflo-schema", "src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "packages", "workflo-utils", "src")))

dbfile = os.path.join(tempfile.gettempdir(), "wfl_repro_auth.db")
if os.path.exists(dbfile):
    os.remove(dbfile)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{dbfile}"
os.environ["REDIS_URL"] = ""

import asyncio  # noqa: E402
from datetime import timedelta  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from app.core.crypto import utc_now, hash_api_key  # noqa: E402
from app.db import database  # noqa: E402
from app.db.models import ApiKey, Organization, Project  # noqa: E402
from app.main import app  # noqa: E402


def expired_key_row():
    async def _mk():
        async with database.async_session_factory() as db:
            org_id = (await db.execute(select(Organization.id))).scalars().first()
            if org_id is None:
                org = Organization(name="exp-org")
                db.add(org)
                await db.flush()
                org_id = org.id
            if (await db.get(Project, "exp-proj")) is None:
                db.add(Project(id="exp-proj", org_id=org_id, name="exp"))
                await db.flush()
            db.add(ApiKey(
                project_id="exp-proj",
                key_hash=hash_api_key("wfl_expired_key_test"),
                label="expired-test",
                scopes=["run_tests"],
                expires_at=utc_now() - timedelta(days=1),
            ))
            await db.commit()
    asyncio.run(_mk())


results = []
with TestClient(app) as c:
    # R2: login with bad creds must be a clean 400, not NameError
    r = c.post("/v1/auth/login", data={"email": "nobody@x.com", "password": "wrong"})
    results.append(("login bad creds (R2)", r.status_code, r.text[:100]))

    # R4 order: demo project + key exist FIRST, then signup
    r = c.post("/v1/auth/demo-token")
    demo_key = r.json().get("api_key", "") if r.status_code == 200 else ""
    results.append(("demo-token first (R4 setup)", r.status_code, r.text[:60]))

    r = c.post("/v1/auth/signup", data={"email": "alice@x.com", "password": "secret123"})
    results.append(("signup after demo project (R4)", r.status_code, r.text[:80]))

    r = c.post("/v1/auth/signup", data={"email": "alice@x.com", "password": "secret123"})
    results.append(("signup duplicate email", r.status_code, r.text[:80]))

    r = c.post("/v1/auth/signup", data={"email": "bob@x.com", "password": "secret456"})
    results.append(("signup second user (R4)", r.status_code, r.text[:60]))

    # R2: real login with the just-registered user
    r = c.post("/v1/auth/login", data={"email": "bob@x.com", "password": "secret456"})
    results.append(("login real user (R2)", r.status_code, (r.text[:80] if r.status_code != 200 else "tokens issued") ))

    # /v1/runs with the demo key
    r = c.post("/v1/runs",
               json={"repo_url": "https://example.com/repo.git", "probe_groups": ["test"]},
               headers={"X-API-Key": demo_key})
    results.append(("POST /v1/runs with demo key", r.status_code, r.text[:100]))

    # R3: an EXPIRED api key must 401, not TypeError->500
    expired_key_row()
    r = c.get("/v1/keys", headers={"X-API-Key": "wfl_expired_key_test"})
    results.append(("expired key (R3)", r.status_code, r.text[:100]))

for name, status, body in results:
    print(f"== {name} -> {status}")
    print(f"    {body}")
