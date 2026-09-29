"""InferenceProvenance schema contract tests.

The cost-rail fields (input_tokens/output_tokens/inference_seconds) are
OPTIONAL with defaults so pre-benchmark receipts stay schema-valid, while
extra="forbid" still rejects unknown keys.
"""

import pytest
from pydantic import ValidationError

from workflo_schema.inference import InferenceProvenance


class TestInferenceProvenance:
    def test_minimal_provenance_still_valid(self):
        """A provenance record without cost fields validates (old receipts)."""
        prov = InferenceProvenance(mode="direct", model="m")
        assert prov.input_tokens == 0
        assert prov.output_tokens == 0
        assert prov.inference_seconds == 0.0

    def test_cost_rail_fields_accepted(self):
        prov = InferenceProvenance(
            mode="direct", model="m", requests=3,
            input_tokens=333, output_tokens=666, inference_seconds=1.25,
        )
        assert prov.input_tokens == 333
        assert prov.output_tokens == 666
        assert prov.inference_seconds == 1.25

    def test_negative_tokens_rejected(self):
        with pytest.raises(ValidationError):
            InferenceProvenance(mode="direct", model="m", input_tokens=-1)

    def test_extra_fields_still_forbidden(self):
        with pytest.raises(ValidationError):
            InferenceProvenance(mode="direct", model="m", surprise=1)

    def test_gateway_mode_provenance_with_cost_rail(self):
        prov = InferenceProvenance(
            mode="gateway", model="qwen3-4b", gateway_url="http://cp/v1",
            requests=2, input_tokens=100, output_tokens=50,
            inference_seconds=2.0,
            request_ids=["req-1", "req-2"],
        )
        assert prov.mode == "gateway"
        assert prov.request_ids == ["req-1", "req-2"]
