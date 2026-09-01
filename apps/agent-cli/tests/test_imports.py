"""Smoke-import tests for the Tenant Shield agent CLI."""

import click

from workflo_agent.cli import main
from workflo_agent.client import ControlPlaneClient
from workflo_agent.commands.auth import auth
from workflo_agent.commands.test import test
from workflo_agent.commands.runs import runs
from workflo_agent.ui.prompts import GOAL_CHOICES


def test_main_is_callable():
    assert callable(main)


def test_control_plane_client_exists():
    assert ControlPlaneClient is not None
    assert isinstance(ControlPlaneClient, type)


def test_auth_command_is_click_group():
    assert isinstance(auth, click.Group)


def test_test_command_is_click_command():
    assert isinstance(test, click.Command)


def test_runs_command_is_click_group():
    assert isinstance(runs, click.Group)


def test_goal_choices_has_six_expected_keys():
    expected = {"smoke", "security", "integration", "mobile", "regression", "custom"}
    assert set(GOAL_CHOICES.keys()) == expected
    assert len(GOAL_CHOICES) == 6
