"""API key management endpoints — used by the Dashboard."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import ApiKey
from app.services.api_key_service import ApiKeyService
from app.core.security import require_api_key, require_scope

router = APIRouter(prefix="/keys", tags=["keys"])


class CreateKeyRequest(BaseModel):
    project_id: str = "default"
    label: str = "My API Key"
    scopes: list[str] = ["run_tests", "read_reports"]


class KeyResponse(BaseModel):
    id: str
    project_id: str
    label: str
    scopes: list[str]
    created_at: str
    last_used: str | None = None


class CreateKeyResponse(KeyResponse):
    raw_key: str


async def _ensure_default_project(db: AsyncSession, api_key: ApiKey | None = None):
    from app.db.models import Project, Organization
    proj = await db.get(Project, "default")
    if not proj:
        org = Organization(name="Default Org")
        db.add(org)
        await db.flush()
        proj = Project(id="default", org_id=org.id, name="Default Project")
        db.add(proj)
        await db.commit()
    return proj


@router.post("", response_model=CreateKeyResponse)
async def create_key(req: CreateKeyRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Create a new API key. Returns the raw key once — store it securely."""
    # Allow creation without auth for bootstrapping (first key)
    await _ensure_default_project(db)
    service = ApiKeyService(db)
    raw_key, record = await service.create_key(req.project_id, req.label, req.scopes)
    return CreateKeyResponse(
        id=record.id,
        project_id=record.project_id,
        label=record.label,
        scopes=record.scopes,
        created_at=record.created_at.isoformat() if record.created_at else "",
        last_used=None,
        raw_key=raw_key,
    )


@router.get("", response_model=list[KeyResponse])
async def list_keys(api_key: ApiKey = Depends(require_api_key), db: AsyncSession = Depends(get_db)):
    service = ApiKeyService(db)
    keys = await service.list_keys(api_key.project_id)
    return [
        KeyResponse(
            id=k.id,
            project_id=k.project_id,
            label=k.label,
            scopes=k.scopes,
            created_at=k.created_at.isoformat() if k.created_at else "",
            last_used=k.last_used.isoformat() if k.last_used else None,
        )
        for k in keys
    ]


@router.delete("/{key_id}")
async def revoke_key(key_id: str, api_key: ApiKey = Depends(require_api_key), db: AsyncSession = Depends(get_db)):
    service = ApiKeyService(db)
    ok = await service.revoke_key(key_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"status": "revoked", "id": key_id}
