"""Tests for authentication."""
import pytest
from app.core.auth import User, extract_bearer_token
from app.core.exceptions import CortexAuthError
from app.middleware.auth import is_public_path


def test_extract_bearer_token_valid():
    """Valid bearer token is extracted."""
    token = extract_bearer_token("Bearer abc.def.ghi")
    assert token == "abc.def.ghi"


def test_extract_bearer_token_missing():
    """Missing header raises CortexAuthError."""
    with pytest.raises(CortexAuthError):
        extract_bearer_token(None)


def test_extract_bearer_token_malformed():
    """Malformed header raises CortexAuthError."""
    with pytest.raises(CortexAuthError):
        extract_bearer_token("abc.def.ghi")
    with pytest.raises(CortexAuthError):
        extract_bearer_token("Basic abc")


def test_user_role_check():
    """User role check works."""
    user = User(subject="u1", email="e@e.com", name="n", roles=["viewer"])
    assert user.has_role("viewer")
    assert not user.has_role("admin")
    assert not user.is_admin

    admin = User(subject="u2", email=None, name=None, roles=["admin"])
    assert admin.is_admin
    assert admin.has_role("viewer")  # admin can do everything


def test_public_paths():
    """Health and metrics are public paths."""
    assert is_public_path("/health")
    assert is_public_path("/metrics")
    assert not is_public_path("/assets/urn:li:dataset:foo")
