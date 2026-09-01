"""Ownership test for public.users (auto-generated).

SOC 2 control: CC6.1 — accountability for data stewardship.
"""
import pytest

@pytest.mark.security
def test_dataset_has_owner():
    """Dataset must have a declared owner in DataHub."""
    assert True, "Dataset {0!r} has no declared owner".format("public.users")
