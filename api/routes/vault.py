"""
PHASE: 29
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/91_PHASE_29_ADVANCED_VAULT_OPERATIONS_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/fa98328c-ff31-452a-9668-808df53aa5a3/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.dependencies import get_vault_manager, require_permissions
from api.dto import MetaBlock, SuccessEnvelope
from core.security.auth_context import RequestContext

router = APIRouter()


class VaultRotateResponse(BaseModel):
    status: str
    new_key_id: str


class VaultBackupResponse(BaseModel):
    backup_data: Dict[str, Any]


class VaultRestoreRequest(BaseModel):
    backup_data: Dict[str, Any]


class VaultRestoreResponse(BaseModel):
    status: str
    version: int


@router.post("/vault/rotate")
async def rotate_vault(
    request: Request,
    _ctx: RequestContext = Depends(require_permissions(["vault.admin"])),
    vault: Any = Depends(get_vault_manager),
) -> Response:
    """POST /api/v1/vault/rotate

    Triggers cryptographic master key rotation. Decrypts all entries, re-encrypts
    with the new key, and updates key IDs.
    """
    new_key_id = await vault.rotate_master_key()
    data = VaultRotateResponse(status="success", new_key_id=new_key_id)

    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()
    envelope = SuccessEnvelope[VaultRotateResponse](data=data, meta=meta)
    return JSONResponse(status_code=200, content=envelope.model_dump(mode="json"))


@router.post("/vault/backup")
async def backup_vault(
    request: Request,
    _ctx: RequestContext = Depends(require_permissions(["vault.admin"])),
    vault: Any = Depends(get_vault_manager),
) -> Response:
    """POST /api/v1/vault/backup

    Returns the encrypted vault metadata block for backup purposes.
    """
    data = VaultBackupResponse(backup_data=vault._secrets_metadata)

    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()
    envelope = SuccessEnvelope[VaultBackupResponse](data=data, meta=meta)
    return JSONResponse(status_code=200, content=envelope.model_dump(mode="json"))


@router.post("/vault/restore")
async def restore_vault(
    request: Request,
    payload: VaultRestoreRequest,
    _ctx: RequestContext = Depends(require_permissions(["vault.admin"])),
    vault: Any = Depends(get_vault_manager),
) -> Response:
    """POST /api/v1/vault/restore

    Restores vault from encrypted backup metadata, writing atomically to disk.
    """
    import json
    import os

    backup = payload.backup_data

    # Validate backup schema version
    if (
        not isinstance(backup, dict)
        or "version" not in backup
        or "entries" not in backup
    ):
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="Invalid vault backup format.")

    version = backup["version"]

    # Transactional Atomic write
    tmp_path = vault.secrets_path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(backup, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, vault.secrets_path)
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        from fastapi import HTTPException

        raise HTTPException(
            status_code=500, detail=f"Failed to restore vault files: {str(e)}"
        )

    # Re-initialize vault with restored secrets
    await vault.initialize()

    data = VaultRestoreResponse(status="success", version=version)

    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()
    envelope = SuccessEnvelope[VaultRestoreResponse](data=data, meta=meta)
    return JSONResponse(status_code=200, content=envelope.model_dump(mode="json"))
