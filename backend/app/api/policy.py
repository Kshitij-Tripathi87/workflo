"""Policy management endpoints — defaults and validation.

Exposes:
  GET  /policy/defaults       — server-side baseline policy list
  POST /policy/validate       — validate a policy list against the engine
  GET  /policy/examples       — a few example policies to copy/paste
"""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import User
from app.engine.policy import (
    Policy,
    evaluate_policies,
    combine_verdict,
    policies_from_dicts,
)
from app.middleware.auth import get_current_user, require_role


router = APIRouter(prefix="/policy", tags=["policy"])


# Server-side defaults — applied when the user has no inline policy and
# no cortex.yml. Conservative: blocks on critical severity, warns on
# ML downstream impact.
DEFAULT_POLICIES: List[Dict[str, Any]] = [
    {
        "name": "Cortex Autopilot default — block on critical severity",
        "max_severity": 75,
        "max_blast_radius": 10,
        "action": "block",
    },
    {
        "name": "Cortex Autopilot default — warn on ML downstream impact",
        "max_severity": 50,
        "max_blast_radius": 3,
        "action": "warn",
    },
]


EXAMPLE_POLICIES: List[Dict[str, Any]] = [
    {
        "name": "Block any change to critical assets",
        "max_severity": 0,
        "action": "block",
    },
    {
        "name": "Require owner on gold assets",
        "require_owner": True,
        "action": "block",
    },
    {
        "name": "Warn before large blast radius",
        "max_blast_radius": 5,
        "action": "warn",
    },
]


@router.get("/defaults")
async def get_defaults(user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """Return the server-side default policy list.

    The Impact Gate uses this when the user's PR has neither an inline
    policy nor a cortex.yml in the repo.
    """
    return {"policies": DEFAULT_POLICIES}


@router.get("/examples")
async def get_examples(user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """Return a curated set of example policies."""
    return {"policies": EXAMPLE_POLICIES}


class ValidateRequest(BaseModel):
    policies: List[Dict[str, Any]] = Field(min_length=0, max_length=50)
    severity: float = Field(ge=0, le=100)
    blast_radius: int = Field(ge=0, le=10_000)
    has_owner: bool = True


class ValidateResponse(BaseModel):
    verdict: str
    results: List[Dict[str, Any]]


@router.post("/validate", response_model=ValidateResponse)
async def validate_policies(
    payload: ValidateRequest,
    user: User = Depends(require_role("analyst")),
) -> ValidateResponse:
    """Dry-run a policy list against a hypothetical severity/blast-radius.

    Useful for the "tweak loop" in the UI — adjust thresholds and
    immediately see the verdict flip.
    """
    policies: List[Policy] = policies_from_dicts(payload.policies)
    if len(policies) != len(payload.policies):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "POLICY_INVALID_CONFIG",
                "message": "One or more policies could not be parsed.",
                "hint": "See docs/policy.md for supported fields.",
            },
        )

    results = evaluate_policies(
        policies=policies,
        severity=payload.severity,
        blast_radius=payload.blast_radius,
        has_owner=payload.has_owner,
    )
    verdict = combine_verdict(results)
    return ValidateResponse(
        verdict=verdict,
        results=[r.model_dump() for r in results],
    )
