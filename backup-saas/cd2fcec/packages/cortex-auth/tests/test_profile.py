"""Tests for the profile manager (multiple accounts and organizations)."""

from pathlib import Path

import pytest

from cortex_auth.profile import AuthProfile, ProfileError, ProfileManager


@pytest.fixture
def manager(tmp_path: Path) -> ProfileManager:
    return ProfileManager(tmp_path / "config.json")


def _make_profile(name: str = "cortex-labs") -> AuthProfile:
    return AuthProfile(
        name=name,
        product="workflo",
        client_id="workflo_cli",
        base_url="https://auth.cortex.dev",
        scopes=["openid", "profile", "workflo:runs:create"],
    )


class TestProfileCRUD:
    def test_add_and_get_profile(self, manager: ProfileManager):
        profile = _make_profile()
        manager.add_profile(profile)
        loaded = manager.get_profile("cortex-labs")
        assert loaded.name == "cortex-labs"
        assert loaded.client_id == "workflo_cli"

    def test_get_profile_raises_on_missing(self, manager: ProfileManager):
        with pytest.raises(ProfileError):
            manager.get_profile("does-not-exist")

    def test_list_profiles(self, manager: ProfileManager):
        manager.add_profile(_make_profile("personal"))
        manager.add_profile(_make_profile("work"))
        names = [p.name for p in manager.list_profiles()]
        assert set(names) == {"personal", "work"}

    def test_remove_profile(self, manager: ProfileManager):
        manager.add_profile(_make_profile("personal"))
        manager.remove_profile("personal")
        assert manager.list_profiles() == []

    def test_remove_profile_clears_active(self, manager: ProfileManager):
        manager.add_profile(_make_profile("personal"))
        manager.set_active_profile("personal")
        manager.remove_profile("personal")
        assert manager.get_active_profile_name() is None

    def test_update_profile(self, manager: ProfileManager):
        manager.add_profile(_make_profile())
        manager.update_profile("cortex-labs", email="aarav@cortex.dev", organization_name="Cortex Labs")
        loaded = manager.get_profile("cortex-labs")
        assert loaded.email == "aarav@cortex.dev"
        assert loaded.organization_name == "Cortex Labs"


class TestActiveProfile:
    def test_set_active_profile(self, manager: ProfileManager):
        manager.add_profile(_make_profile("cortex-labs"))
        manager.set_active_profile("cortex-labs")
        assert manager.get_active_profile_name() == "cortex-labs"

    def test_set_active_unknown_raises(self, manager: ProfileManager):
        with pytest.raises(ProfileError):
            manager.set_active_profile("ghost")

    def test_get_active_profile_returns_none_when_unset(self, manager: ProfileManager):
        assert manager.get_active_profile() is None

    def test_get_active_profile(self, manager: ProfileManager):
        manager.add_profile(_make_profile("cortex-labs"))
        manager.set_active_profile("cortex-labs")
        active = manager.get_active_profile()
        assert active is not None
        assert active.name == "cortex-labs"


class TestOrgWorkspaceSelection:
    def test_set_active_org_and_workspace(self, manager: ProfileManager):
        manager.add_profile(_make_profile())
        manager.set_active_org("cortex-labs", "org_456", "Cortex Labs")
        manager.set_active_workspace("cortex-labs", "ws_789", "Engineering")
        loaded = manager.get_profile("cortex-labs")
        assert loaded.active_organization_id == "org_456"
        assert loaded.organization_name == "Cortex Labs"
        assert loaded.active_workspace_id == "ws_789"
        assert loaded.workspace_name == "Engineering"


class TestPersistence:
    def test_reload_from_disk(self, tmp_path: Path):
        path = tmp_path / "config.json"
        m1 = ProfileManager(path)
        m1.add_profile(_make_profile("cortex-labs"))
        m1.set_active_profile("cortex-labs")
        m2 = ProfileManager(path)
        profiles = m2.list_profiles()
        assert len(profiles) == 1
        assert m2.get_active_profile_name() == "cortex-labs"

    def test_corrupt_config_raises(self, tmp_path: Path):
        path = tmp_path / "config.json"
        path.write_text("not json {")
        manager = ProfileManager(path)
        with pytest.raises(ProfileError):
            manager.load()
