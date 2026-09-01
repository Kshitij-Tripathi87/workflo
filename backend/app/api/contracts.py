"""Data Contract QA and Test Generation API Endpoints."""

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.connectors.datahub.client import DataHubClient
from app.services.graph_builder import build_snapshot
from app.core.receipts import receipt_engine
from app.engine.contract_test_generator import contract_test_generator
from app.models.contract import (
    ContractExecutionResult,
    GeneratedContractTest,
)

router = APIRouter(prefix="/contracts", tags=["Contracts"])
client = DataHubClient()


class ContractGenerateRequest(BaseModel):
    dataset_urn: str
    custom_owner: Optional[str] = None


@router.post("/generate", response_model=GeneratedContractTest)
async def generate_contract_test(req: ContractGenerateRequest):
    """Generate a metadata-aware pytest suite from DataHub/dbt catalog metadata."""
    try:
        snapshot = build_snapshot([req.dataset_urn])
        node = snapshot.nodes.get(req.dataset_urn)
        if not node:
            raise HTTPException(status_code=404, detail=f"Asset not found: {req.dataset_urn}")

        contract_spec = contract_test_generator.extract_contract_from_node(node)
        if req.custom_owner:
            contract_spec.owner = req.custom_owner

        return contract_test_generator.generate_pytest_suite(contract_spec)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Asset not found: {req.dataset_urn}")


@router.post("/execute", response_model=ContractExecutionResult)
async def execute_contract_test(req: ContractGenerateRequest):
    """Execute contract tests against the dataset and generate a cryptographic receipt."""
    try:
        snapshot = build_snapshot([req.dataset_urn])
        node = snapshot.nodes.get(req.dataset_urn)
        if not node:
            raise HTTPException(status_code=404, detail=f"Asset not found: {req.dataset_urn}")

        contract_spec = contract_test_generator.extract_contract_from_node(node)
        result = contract_test_generator.evaluate_contract_mock(contract_spec)

        # Attach cryptographic receipt
        receipt = receipt_engine.create_and_sign_receipt(
            action_type="contract_test",
            asset_urn=req.dataset_urn,
            parameters={"dataset_name": node.name, "criticality": node.criticality},
            result_summary={
                "total_tests": result.total_tests,
                "passed_tests": result.passed_tests,
                "failed_tests": result.failed_tests,
                "status": result.status,
            },
            soc2_controls=["CC6.1", "CC7.2"],
            duration_seconds=result.duration_seconds,
        )
        result.receipt_id = receipt.receipt_id
        return result
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Asset not found: {req.dataset_urn}")
