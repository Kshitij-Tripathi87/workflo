import os
import requests


class AuthManager:
    def __init__(self, api_base_url=None):
        self.api_base_url = api_base_url or os.getenv("API_BASE_URL", "https://api.workflowpro.com")

    def login(self, email, password, tenant_id):
        response = requests.post(
            f"{self.api_base_url}/api/v1/auth/login",
            json={"email": email, "password": password},
            headers={"X-Tenant-ID": tenant_id},
        )
        response.raise_for_status()
        data = response.json()
        return data.get("token")

    def login_as_tenant_admin(self, tenant_id):
        email = os.getenv(f"ADMIN_EMAIL_{tenant_id.upper()}")
        password = os.getenv(f"ADMIN_PASSWORD_{tenant_id.upper()}")
        return self.login(email, password, tenant_id)
