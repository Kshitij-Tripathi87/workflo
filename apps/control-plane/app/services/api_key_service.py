"""Service-layer logic for API key management."""

import secrets
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ApiKey, Project, Organization
from app.core.crypto import hash_api_key, utc_now, verify_api_key


class ApiKeyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_key(self, project_id: str, label: str = "", scopes: list[str] | None = None) -> tuple[str, ApiKey]:
        """Create a new API key. Returns (raw_key, api_key_record)."""
        raw_key = f"wf_live_{secrets.token_urlsafe(32)}"
        key_hash = hash_api_key(raw_key)

        record = ApiKey(
            project_id=project_id,
            key_hash=key_hash,
            label=label,
            scopes=scopes or ["run_tests", "read_reports"],
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)

        # Create default org/project if they don't exist yet
        project = await self.db.get(Project, project_id)
        if not project:
            # Auto-create a default project for dev
            org = Organization(name="Default Org")
            self.db.add(org)
            await self.db.flush()
            project = Project(id=project_id, org_id=org.id, name="Default Project")
            self.db.add(project)
            await self.db.commit()

        return raw_key, record

    async def validate_key(self, raw_key: str) -> ApiKey | None:
        """Validate a raw API key and return the record if valid."""
        stmt = select(ApiKey)
        result = await self.db.execute(stmt)
        for record in result.scalars():
            if verify_api_key(raw_key, record.key_hash):
                # Check expiration (naive UTC == naive UTC; see crypto.utc_now)
                if record.expires_at and record.expires_at < utc_now():
                    return None
                # Update last_used
                record.last_used = utc_now()
                await self.db.commit()
                return record
        return None

    async def list_keys(self, project_id: str) -> list[ApiKey]:
        stmt = select(ApiKey).where(ApiKey.project_id == project_id)
        result = await self.db.execute(stmt)
        return list(result.scalars())

    async def revoke_key(self, key_id: str) -> bool:
        record = await self.db.get(ApiKey, key_id)
        if record:
            await self.db.delete(record)
            await self.db.commit()
            return True
        return False
