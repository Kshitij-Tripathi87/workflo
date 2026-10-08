"""Tests for merged Workflo merged capabilities."""

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.models.asset import AssetNode
from app.models.contract import ContractSpec, ColumnConstraint
from app.engine.contract_test_generator import contract_test_generator
from app.core.receipts import receipt_engine
from app.engine.compliance import compliance_engine
from app.models.asset import GraphSnapshot


def test_contract_test_generation():
    """Test generating metadata-aware pytest data contracts."""
    node = AssetNode(
        urn="urn:li:dataset:(snowflake,analytics.fact_orders,PROD)",
        name="fact_orders",
        owner="analytics-team",
        schema_fields=["order_id:INTEGER", "customer_id:INTEGER", "total_amount:FLOAT"],
        upstream=["urn:li:dataset:(snowflake,raw.orders,PROD)"],
        criticality="high",
    )

    spec = contract_test_generator.extract_contract_from_node(node)
    assert spec.dataset_name == "fact_orders"
    assert spec.owner == "analytics-team"
    assert len(spec.columns) == 3

    generated = contract_test_generator.generate_pytest_suite(spec)
    assert generated.dataset_name == "fact_orders"
    assert "class TestFactOrdersSchemaContract:" in generated.test_code
    assert "test_expected_columns_present" in generated.test_code
    assert "test_primary_key_uniqueness" in generated.test_code
    assert "CC6.1" in generated.soc2_controls
    assert "CC7.2" in generated.soc2_controls
    assert generated.integrity_score > 80.0


def test_contract_execution():
    """Test mock execution of contract tests."""
    spec = ContractSpec(
        dataset_urn="urn:li:dataset:(snowflake,analytics.dim_customers,PROD)",
        dataset_name="dim_customers",
        owner="crm-team",
        columns=[
            ColumnConstraint(name="customer_id", data_type="INT", is_primary_key=True, nullable=False),
            ColumnConstraint(name="email", data_type="VARCHAR", nullable=True),
        ],
        upstream_lineage=["urn:li:dataset:(snowflake,raw.customers,PROD)"],
        criticality="high",
    )

    res = contract_test_generator.evaluate_contract_mock(spec)
    assert res.status == "passed"
    assert res.total_tests > 0
    assert res.failed_tests == 0
    assert res.soc2_compliance_met is True


def test_cryptographic_receipt_signing_and_verification():
    """Test signing and verifying receipts with tamper detection."""
    receipt = receipt_engine.create_and_sign_receipt(
        action_type="future_search",
        asset_urn="urn:li:dataset:(snowflake,analytics.fact_orders,PROD)",
        parameters={"objective": "minimize risk"},
        result_summary={"status": "optimal"},
    )

    assert receipt.receipt_id.startswith("wf://receipts/")
    assert receipt.signature is not None
    assert receipt.teardown_proof is not None
    assert receipt.teardown_proof.filesystem_wipe_method == "tmpfs_umount"

    # Verify untampered receipt
    verification = receipt_engine.verify_receipt(receipt)
    assert verification.is_valid is True
    assert verification.tamper_detected is False

    # Simulate payload tampering
    receipt.result_summary["status"] = "tampered_result"
    tampered_verification = receipt_engine.verify_receipt(receipt)
    assert tampered_verification.is_valid is False
    assert tampered_verification.tamper_detected is True


def test_soc2_compliance_engine():
    """Test evaluating catalog assets against AICPA SOC 2 controls."""
    node1 = AssetNode(
        urn="urn:li:dataset:(snowflake,analytics.users,PROD)",
        name="users",
        owner="security-team",
        schema_fields=["id:INT", "email:VARCHAR"],
        criticality="critical",
    )
    node2 = AssetNode(
        urn="urn:li:dataset:(snowflake,analytics.orphan_table,PROD)",
        name="orphan_table",
        owner=None,  # Unassigned critical asset
        schema_fields=[],
        criticality="critical",
    )

    graph = GraphSnapshot(
        nodes={
            str(node1.urn): node1,
            str(node2.urn): node2,
        },
        edges=[],
    )

    report = compliance_engine.evaluate_compliance(graph)
    assert report.total_assets == 2
    assert "CC6.1" in report.controls
    assert "CC7.2" in report.controls
    assert "orphan_table" in report.unowned_critical_assets
    assert report.controls["CC6.1"].status != "compliant"


@pytest.mark.asyncio
async def test_merged_api_endpoints():
    """Test FastAPI REST endpoints for contracts, receipts, and compliance."""
    test_urn = "urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Test /contracts/generate
        res = await ac.post(
            "/contracts/generate",
            json={"dataset_urn": test_urn},
        )
        assert res.status_code == 200
        data = res.json()
        assert "test_code" in data
        assert "CC6.1" in data["soc2_controls"]

        # 2. Test /contracts/execute
        res_exec = await ac.post(
            "/contracts/execute",
            json={"dataset_urn": test_urn},
        )
        assert res_exec.status_code == 200
        exec_data = res_exec.json()
        assert exec_data["receipt_id"] is not None

        # 3. Test /compliance/report
        res_comp = await ac.get("/compliance/report")
        assert res_comp.status_code == 200
        comp_data = res_comp.json()
        assert "controls" in comp_data
        assert "CC6.1" in comp_data["controls"]

        # 4. Test /future-search/run includes cryptographic receipt
        res_fs = await ac.post(
            "/future-search/run",
            json={"asset_urn": test_urn, "objective": "minimize incident risk"},
        )
        assert res_fs.status_code == 200
        fs_data = res_fs.json()
        assert fs_data.get("receipt") is not None
        assert fs_data["receipt"]["receipt_id"].startswith("wf://receipts/")
