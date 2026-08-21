"""End-to-end test of the CLI device flow against the real control-plane server.

This script:
1. Requests a device code via the CLI's AuthSession
2. Automatically approves it via the control-plane's /device endpoint
3. Lets the CLI poll for the token
4. Verifies auth status shows the logged-in session
5. Logs out

Run with:
    WORKFLO_AUTH_BASE_URL=http://localhost:8001 python test_device_flow_e2e.py
"""

import os
import sys
import time
import threading
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "workflo-cli", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages", "cortex-auth", "src"))

from cortex_auth.session import AuthSession
from cortex_auth.scopes import WORKFLO_SCOPES, PRODUCT_CLIENT_IDS


BASE_URL = os.environ.get("WORKFLO_AUTH_BASE_URL", "http://localhost:8001")


def auto_approve(user_code: str):
    """Automatically approve the device code via the control-plane."""
    time.sleep(2)  # wait for the device code to be stored and first poll to pass
    resp = httpx.post(
        f"{BASE_URL}/device",
        data={"user_code": user_code, "action": "allow"},
    )
    print(f"[auto-approve] HTTP {resp.status_code}")
    return resp.status_code == 200


def main():
    print(f"Testing device flow against {BASE_URL}")

    session = AuthSession(
        product="workflo",
        client_id=PRODUCT_CLIENT_IDS["workflo"],
        base_url=BASE_URL,
        scopes=WORKFLO_SCOPES,
    )

    # Monkey-patch request_device_code to auto-approve after getting the code
    original_request = session._client.request_device_code

    def patched_request():
        dc = original_request()
        print(f"Device code requested. User code: {dc.user_code}")
        print(f"Verification URI: {dc.verification_uri_complete}")
        threading.Thread(
            target=auto_approve, args=(dc.user_code,), daemon=True
        ).start()
        return dc

    session._client.request_device_code = patched_request

    # Run the full login flow (requests device code + polls for token + saves session)
    print("Running full login flow...")
    result = session.login(
        profile_name="e2e-test",
        open_browser=False,
    )
    print(f"Got access token: {result.session.access_token[:20]}...")
    print(f"Scopes: {' '.join(result.session.scopes)}")
    print(f"Credential store: {result.backend_name}")

    # Step 3: verify status
    print("\nVerifying auth status...")
    status = session.status()
    if status is None:
        print("FAIL: status returned None")
        return 1

    print(f"  Email: {status.email}")
    print(f"  Organization: {status.organization_name or '(none)'}")
    print(f"  Workspace: {status.workspace_name or status.workspace_id or '(none)'}")
    print(f"  Token valid: {status.is_access_token_valid()}")

    # Step 4: test get_access_token (silent refresh)
    print("\nTesting get_access_token...")
    access_token = session.get_access_token()
    print(f"Access token: {access_token[:20]}...")

    # Step 5: logout (revokes token, clears credential store)
    print("\nTesting logout...")
    session.logout()
    print("Logged out.")

    # Step 6: verify status is None after logout
    status_after = session.status()
    if status_after is not None:
        print("FAIL: status should be None after logout")
        return 1
    print("Status after logout: None (correct)")

    print("\nAll device flow tests passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
