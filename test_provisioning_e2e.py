"""End-to-end test of key provisioning against real control-plane.

This script:
1. Runs device flow login (auth)
2. Provisions a key (POST /v1/auth/keys/provision)
3. Fetches the key by key_id (GET /v1/auth/keys/{key_id})
4. Revokes the key (POST /v1/auth/keys/{key_id}/revoke)
5. Verifies revocation is reflected (GET shows status=revoked)

Run with:
    WORKFLO_AUTH_BASE_URL=http://localhost:8001 python test_provisioning_e2e.py
"""

import os
import sys
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "workflo-cli", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages", "cortex-auth", "src"))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import httpx

from cortex_auth.session import AuthSession
from cortex_auth.scopes import WORKFLO_SCOPES, PRODUCT_CLIENT_IDS


BASE_URL = os.environ.get("WORKFLO_AUTH_BASE_URL", "http://localhost:8001")


def auto_approve(user_code: str):
    """Auto-approve device flow."""
    time.sleep(2)
    httpx.post(
        f"{BASE_URL}/device",
        data={"user_code": user_code, "action": "allow"},
    )


def main():
    print(f"Testing key provisioning against {BASE_URL}")

    # Step 1: login via device flow
    print("\n[1] Logging in via device flow...")
    session = AuthSession(
        product="workflo",
        client_id=PRODUCT_CLIENT_IDS["workflo"],
        base_url=BASE_URL,
        scopes=WORKFLO_SCOPES,
    )
    original_request = session._client.request_device_code
    captured = {}

    def patched_request():
        dc = original_request()
        captured["user_code"] = dc.user_code
        threading.Thread(target=auto_approve, args=(dc.user_code,), daemon=True).start()
        return dc

    session._client.request_device_code = patched_request
    result = session.login(profile_name="prov-test", open_browser=False)
    access_token = result.session.access_token
    print(f"  Logged in. Access token: {access_token[:20]}...")

    # Step 2: generate keypair locally, provision public key
    print("\n[2] Generating keypair + provisioning...")
    private_key = Ed25519PrivateKey.generate()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    device_id = "test-device-001"
    resp = httpx.post(
        f"{BASE_URL}/v1/auth/keys/provision",
        json={"public_key": public_pem, "device_id": device_id},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    print(f"  HTTP {resp.status_code}: {resp.json()}")
    assert resp.status_code == 200
    key_id = resp.json()["key_id"]
    fingerprint = resp.json()["fingerprint"]

    # Step 3: fetch the key by key_id
    print("\n[3] Fetching key by key_id...")
    resp = httpx.get(f"{BASE_URL}/v1/auth/keys/{key_id}", timeout=10)
    print(f"  HTTP {resp.status_code}")
    print(f"  Status: {resp.json()['status']}")
    print(f"  Device: {resp.json()['device_id']}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"
    assert resp.json()["device_id"] == device_id

    # Step 4: revoke the key
    print("\n[4] Revoking key...")
    resp = httpx.post(
        f"{BASE_URL}/v1/auth/keys/{key_id}/revoke",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    print(f"  HTTP {resp.status_code}: {resp.json()}")
    assert resp.status_code == 200
    assert resp.json()["revoked"] is True

    # Step 5: verify revocation
    print("\n[5] Verifying revocation reflected...")
    resp = httpx.get(f"{BASE_URL}/v1/auth/keys/{key_id}", timeout=10)
    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"
    print(f"  Status: {resp.json()['status']} (correct)")

    # Step 6: idempotent re-provision (should fail with 409 since revoked)
    print("\n[6] Re-provisioning revoked key (should fail)...")
    resp = httpx.post(
        f"{BASE_URL}/v1/auth/keys/provision",
        json={"public_key": public_pem, "device_id": device_id},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    print(f"  HTTP {resp.status_code}: {resp.json()}")
    assert resp.status_code == 409

    print("\n[OK] All provisioning tests passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
