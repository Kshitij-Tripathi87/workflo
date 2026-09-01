"""Repro: POST /v1/runs 500 sources in the control plane (read-only repro script)."""
import os
import sys
import traceback
import tempfile

sys.path.insert(0, os.path.join(tempfile.gettempdir(), "cp"))  # no-op guard
cp = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "control-plane"))
sys.path.insert(0, cp)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "packages", "workflo-schema", "src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "packages", "workflo-utils", "src")))

dbfile = os.path.join(tempfile.gettempdir(), "wfl_repro_cp.db")
if os.path.exists(dbfile):
    os.remove(dbfile)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{dbfile}"

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

results = []
with TestClient(app, raise_server_exceptions=True) as c:
    for name, call in [
        ("GET /v1/health", lambda: c.get("/v1/health")),
        ("POST /v1/auth/demo-token", lambda: c.post("/v1/auth/demo-token")),
        ("POST /v1/runs", lambda: c.post(
            "/v1/runs",
            json={"repo_url": "https://example.com/repo.git", "probe_groups": ["test"]},
            headers={"X-API-Key": "wfl_" + "a1b2c3d4e5f67890abcdef1234567890"},
        )),
        ("POST /v1/auth/logout-probe /v1/auth/login", lambda: c.post(
            "/v1/auth/login", data={"email": "e@x.com", "password": "p"}
        )),
    ]:
        try:
            r = call()
            results.append((name, r.status_code, r.text[:180]))
        except Exception as e:
            results.append((name, f"EXC {type(e).__name__}", f"{e}"))

for name, status, body in results:
    print(f"==={name} -> {status}")
    print("   ", body.replace("\n", " ")[:220])
