"""One-time API-key provisioning for production.

Run with the schema-owner/bootstrap DSN, RLS enabled, and the configured
credential-encryption key. The raw key is written once to a mode-0600 file
rather than stdout/logs; move it into the approved secret manager and delete
the file securely after verifying the client can authenticate.

Example:
    DATABASE_URL=postgresql+asyncpg://<schema-owner>:.../<db> \
    RLS_ENABLED=true MASTER_KEK_HEX=<64-hex-chars> \
    WORKFLO_BOOTSTRAP_KEY_FILE=/run/secrets/new-workflo-key \
    WORKFLO_BOOTSTRAP_PROJECT_ID=default \
    WORKFLO_BOOTSTRAP_KEY_SCOPES=run_tests,read_reports \
      python -m app.db.bootstrap_api_key
"""

from __future__ import annotations

import asyncio
import json
import os
import stat
from pathlib import Path

from app.core import envelope
from app.core.config import settings
from app.db import database
from app.db.database import async_session_factory, set_tenant_context
from app.services.api_key_service import ApiKeyService


_ALLOWED_SCOPES = {"run_tests", "read_reports"}


async def bootstrap_api_key() -> dict:
    if database.engine.dialect.name != "postgresql":
        raise RuntimeError("API-key provisioning is PostgreSQL-only")
    if not settings.rls_enabled:
        raise RuntimeError("RLS_ENABLED must be true when provisioning a production key")
    kek_error = envelope.availability_error(settings)
    if kek_error:
        raise RuntimeError(f"credential encryption is unavailable: {kek_error}")

    output_raw = os.environ.get("WORKFLO_BOOTSTRAP_KEY_FILE", "").strip()
    if not output_raw:
        raise RuntimeError("WORKFLO_BOOTSTRAP_KEY_FILE must name a protected output file")
    output = Path(output_raw).expanduser()
    project_id = os.environ.get("WORKFLO_BOOTSTRAP_PROJECT_ID", "default").strip()
    label = os.environ.get("WORKFLO_BOOTSTRAP_KEY_LABEL", "initial-workflo-client").strip()
    scopes_raw = os.environ.get("WORKFLO_BOOTSTRAP_KEY_SCOPES", "run_tests,read_reports")
    scopes = sorted({item.strip() for item in scopes_raw.split(",") if item.strip()})
    if not project_id or len(project_id) > 36:
        raise RuntimeError("WORKFLO_BOOTSTRAP_PROJECT_ID must be 1..36 characters")
    if not label or len(label) > 255:
        raise RuntimeError("WORKFLO_BOOTSTRAP_KEY_LABEL must be 1..255 characters")
    if not scopes or not set(scopes).issubset(_ALLOWED_SCOPES):
        raise RuntimeError("key scopes must be a non-empty subset of run_tests,read_reports")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing key file: {output}")

    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    service = None
    record = None
    raw_key = None
    async with async_session_factory() as db:
        service = ApiKeyService(db)
        raw_key, record = await service.create_key(project_id, label, scopes)
        fd = None
        try:
            fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, stat.S_IRUSR | stat.S_IWUSR)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                fd = None
                handle.write(raw_key + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(output, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            if fd is not None:
                os.close(fd)
            output.unlink(missing_ok=True)
            # Do not leave an un-retrievable key active after a failed write.
            await set_tenant_context(db, project_id)
            await service.revoke_key(record.id)
            raise

    result = {
        "status": "created",
        "project_id": project_id,
        "key_id": record.id,
        "label": label,
        "scopes": scopes,
        "secret_file": str(output),
    }
    print(json.dumps(result, indent=2))
    return result


async def _main_async() -> None:
    try:
        await bootstrap_api_key()
    finally:
        await database.engine.dispose()


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
