"""Tests for the Tenant Shield DataHub client package."""

import json
from unittest.mock import patch, MagicMock

import pytest

from workflo_datahub.models import ColumnInfo, DatasetSchema, LineageEdge, DataHubEntity


def _make_schema_fixture():
    return DatasetSchema(
        urn="urn:li:dataset:(urn:li:dataPlatform:postgres,public.x,PROD)",
        name="public.x",
        platform="postgres",
        owner="ali@example.com",
        columns=[
            ColumnInfo(name="id", type="INT", nullable=False, primary_key=True, description="PK"),
            ColumnInfo(name="email", type="STRING", nullable=False),
            ColumnInfo(name="bio", type="TEXT", nullable=True, description=""),
        ],
    )


def _httpx_mock(response_payload, status_code=200):
    """Helper: mock httpx.Client so `with httpx.Client(...) as c: c.post(...)` returns mocked JSON."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = response_payload
    mock_resp.status_code = status_code
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.post.return_value = mock_resp
    mock_client.get.return_value = mock_resp

    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_client
    mock_ctx.__exit__.return_value = False

    mock_cls = MagicMock()
    mock_cls.return_value = mock_ctx
    return mock_cls


class TestModels:
    def test_dataset_schema_serialization_roundtrip(self):
        schema = _make_schema_fixture()
        payload = schema.model_dump()
        restored = DatasetSchema.model_validate(payload)
        assert restored == schema

    def test_lineage_edge_has_mappings(self):
        edge = LineageEdge(
            source_urn="urn:source", target_urn="urn:target",
            column_mappings=[{"source": "a", "target": "b"}],
        )
        assert edge.column_mappings[0]["source"] == "a"

    def test_datahub_entity_defaults(self):
        e = DataHubEntity(urn="urn:li:dataset:(x,y,PROD)", type="dataset", name="x")
        assert e.platform == ""
        assert e.description == ""


class TestDataHubClient:
    @patch("workflo_datahub.client.httpx.Client")
    def test_search_datasets_parses_entities(self, mock_client_cls):
        mock_client_cls.side_effect = lambda *a, **kw: _httpx_mock({
            "data": {
                "search": {
                    "searchResults": {
                        "entities": [
                            {"urn": "urn:1", "type": "dataset", "name": "table1",
                             "platform": {"name": "postgres"}},
                        ]
                    }
                }
            }
        }).return_value

        from workflo_datahub.client import DataHubClient
        client = DataHubClient(server_url="http://localhost:8080")
        results = client.search_datasets("test", limit=1)
        assert len(results) == 1
        assert results[0].urn == "urn:1"
        assert results[0].platform == "postgres"

    @patch("workflo_datahub.client.httpx.Client")
    def test_get_dataset_extracts_columns_and_owner(self, mock_client_cls):
        mock_client_cls.side_effect = lambda *a, **kw: _httpx_mock({
            "data": {"dataset": {
                "urn": "urn:li:dataset:(x,y,PROD)",
                "name": "public.y",
                "platform": {"name": "snowflake"},
                "schemaMetadata": {
                    "fields": [
                        {"fieldPath": "id", "type": "NUMBER", "nullable": False, "primaryKey": True, "description": "PK"},
                        {"fieldPath": "ts", "type": "TIMESTAMP", "nullable": True},
                    ]
                },
                "ownership": {"owners": [{"owner": {"username": "data-team"}}]},
            }}
        }).return_value

        from workflo_datahub.client import DataHubClient
        client = DataHubClient(server_url="http://localhost:8080")
        schema = client.get_dataset("urn:li:dataset:(x,y,PROD)")
        assert schema.name == "public.y"
        assert schema.owner == "data-team"
        assert schema.platform == "snowflake"
        assert len(schema.columns) == 2
        assert schema.columns[0].primary_key is True
        assert schema.columns[1].nullable is True

    @patch("workflo_datahub.client.httpx.Client")
    def test_write_assertion_returns_true_on_success(self, mock_client_cls):
        mock_client_cls.side_effect = lambda *a, **kw: _httpx_mock({}, status_code=200).return_value

        from workflo_datahub.client import DataHubClient
        client = DataHubClient(server_url="http://localhost:8080")
        assert client.write_assertion("urn:1", "assert-1", "passed", "OK") is True


class TestInspector:
    def test_schema_integrity_score(self):
        from workflo_datahub.inspector import MetadataInspector
        client = MagicMock()
        insp = MetadataInspector(client)
        schema = _make_schema_fixture()
        score = insp.schema_integrity_score(schema)
        # All columns: id (3/3), email (2/3, no desc), bio (1/3) = (3+2+1)/9
        assert 0.5 < score < 1.0

    def test_primary_key_columns(self):
        from workflo_datahub.inspector import MetadataInspector
        insp = MetadataInspector(MagicMock())
        schema = _make_schema_fixture()
        assert insp.primary_key_columns(schema) == ["id"]

    def test_nullable_violations_flags_nondescribed_nonnull(self):
        from workflo_datahub.inspector import MetadataInspector
        insp = MetadataInspector(MagicMock())
        schema = _make_schema_fixture()
        # email is non-nullable and lacks description -> flagged
        violations = insp.nullable_violations(schema)
        assert "email" in violations
        assert "id" not in violations  # PK has description


class TestWriteback:
    def test_write_dataset_assertion_calls_api(self):
        from workflo_datahub.client import DataHubClient
        from workflo_datahub.writeback import ResultWriteback

        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_client
        mock_ctx.__exit__.return_value = False

        with patch("workflo_datahub.client.httpx.Client", return_value=mock_ctx):
            client = DataHubClient(server_url="http://localhost:8080")
            wb = ResultWriteback(client)
            ok = wb.write_dataset_assertion("urn:1", "assert-1", passed=True, details="auto")
            assert ok is True


class TestGenerator:
    def test_generate_schema_tests_produces_runnable_code(self):
        from workflo_datahub.generator import TestGenerator
        client = MagicMock()
        client.get_dataset.return_value = _make_schema_fixture()
        gen = TestGenerator(client)
        art = gen.generate_schema_tests("urn:1")
        code = art.test_code

        # Should be importable Python
        import ast
        ast.parse(code)  # raises if syntax invalid

        # Should contain key elements
        assert "DATASET_URN" in code
        assert "test_primary_key_unique" in code
        assert "_NULLABLE_COLUMNS" in code
        assert "_NON_NULLABLE_COLUMNS" in code

    def test_generate_lineage_tests_produces_runnable_code(self):
        from workflo_datahub.generator import TestGenerator
        client = MagicMock()
        client.get_lineage.return_value = [
            LineageEdge(source_urn="urn:s", target_urn="urn:t",
                        source_dataset="src", target_dataset="dst",
                        column_mappings=[{"source": "a", "target": "b"}]),
        ]
        gen = TestGenerator(client)
        art = gen.generate_lineage_tests("urn:1", "UPSTREAM")

        import ast
        ast.parse(art.test_code)
        assert "EXPECTED_EDGES" in art.test_code
        assert "test_lineage_edge_active" in art.test_code

    def test_generate_ownership_tests_reflects_owner_state(self):
        from workflo_datahub.generator import TestGenerator
        client = MagicMock()
        client.get_dataset.return_value = _make_schema_fixture()  # has owner
        gen = TestGenerator(client)
        art = gen.generate_ownership_tests("urn:1")
        assert "True" in art.test_code  # has_owner == True

        # Now without owner
        no_owner = _make_schema_fixture().model_copy(update={"owner": ""})
        client.get_dataset.return_value = no_owner
        art2 = gen.generate_ownership_tests("urn:1")
        assert "False" in art2.test_code

    def test_full_suite_generates_one_artifact_per_test_per_dataset(self):
        from workflo_datahub.generator import TestGenerator
        client = MagicMock()
        client.get_dataset.return_value = _make_schema_fixture()
        client.get_lineage.return_value = []
        gen = TestGenerator(client)
        artifacts = gen.generate_full_suite(["urn:1", "urn:2"])
        # 3 artifacts per dataset (schema + lineage + ownership) × 2 datasets
        assert len(artifacts) == 6

    def test_slug_handles_special_chars(self):
        from workflo_datahub.generator import TestGenerator
        assert TestGenerator._slug("urn:li:dataset:(urn:li:dataPlatform:x,y,PROD)") == \
            "urn_li_dataset_urn_li_dataplatform_x_y_prod"
