"""Cryptographic Receipts and Sandbox Verification API Endpoints."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.receipts import receipt_engine
from app.models.receipt import (
    ReceiptVerificationResponse,
    SignedReceipt,
)

router = APIRouter(prefix="/receipts", tags=["Receipts"])


class SignReceiptRequest(BaseModel):
    action_type: str
    asset_urn: str
    parameters: Dict[str, Any]
    result_summary: Dict[str, Any]
    soc2_controls: Optional[List[str]] = None


@router.post("/sign", response_model=SignedReceipt)
async def sign_receipt(req: SignReceiptRequest):
    """Generate and cryptographically sign a receipt with an ephemeral teardown proof."""
    return receipt_engine.create_and_sign_receipt(
        action_type=req.action_type,
        asset_urn=req.asset_urn,
        parameters=req.parameters,
        result_summary=req.result_summary,
        soc2_controls=req.soc2_controls,
    )


@router.post("/verify", response_model=ReceiptVerificationResponse)
async def verify_receipt(receipt: SignedReceipt):
    """Verify cryptographic signature and tamper-evidence of a receipt."""
    return receipt_engine.verify_receipt(receipt)
