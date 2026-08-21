"""Unit tests for the interactive prompts.

Questionary is never actually invoked - the ``.ask()`` entry points are
mocked so the tests run headless and fast.
"""

from unittest.mock import patch

from workflo_agent.ui.prompts import (
    GOAL_CHOICES,
    prompt_goal,
    prompt_execution_mode,
    prompt_overrides,
)


def test_goal_choices_has_expected_keys():
    expected = {"smoke", "security", "integration", "mobile", "regression", "custom"}
    assert set(GOAL_CHOICES.keys()) == expected


def test_goal_choices_entries_have_label_and_markers():
    for key, value in GOAL_CHOICES.items():
        assert "label" in value, f"missing label for {key}"
        assert "markers" in value, f"missing markers for {key}"
        assert isinstance(value["label"], str)
        assert isinstance(value["markers"], list)


@patch("workflo_agent.ui.prompts.questionary.select")
def test_prompt_goal_returns_selected_choice(mock_select):
    mock_select.return_value.ask.return_value = "security"
    result = prompt_goal()
    assert result == "security"
    mock_select.assert_called_once()
    assert mock_select.return_value.ask.called


@patch("workflo_agent.ui.prompts.questionary.select")
def test_prompt_goal_defaults_to_smoke_when_answer_falsy(mock_select):
    mock_select.return_value.ask.return_value = None
    result = prompt_goal()
    assert result == "smoke"


@patch("workflo_agent.ui.prompts.questionary.select")
def test_prompt_execution_mode_returns_cloud(mock_select):
    mock_select.return_value.ask.return_value = "cloud"
    result = prompt_execution_mode()
    assert result == "cloud"
    mock_select.assert_called_once()


@patch("workflo_agent.ui.prompts.questionary.select")
def test_prompt_execution_mode_returns_local(mock_select):
    mock_select.return_value.ask.return_value = "local"
    result = prompt_execution_mode()
    assert result == "local"


@patch("workflo_agent.ui.prompts.questionary.select")
def test_prompt_execution_mode_defaults_to_cloud_when_falsy(mock_select):
    mock_select.return_value.ask.return_value = None
    result = prompt_execution_mode()
    assert result == "cloud"


@patch("workflo_agent.ui.prompts.questionary.text")
def test_prompt_overrides_returns_expected_keys(mock_text):
    mock_text.return_value.ask.side_effect = ["staging", "8", "3"]
    result = prompt_overrides()
    assert set(result.keys()) == {"TEST_ENV", "PARALLELISM", "RETRIES"}
    assert result == {"TEST_ENV": "staging", "PARALLELISM": "8", "RETRIES": "3"}
    assert mock_text.call_count == 3


@patch("workflo_agent.ui.prompts.questionary.text")
def test_prompt_overrides_passes_correct_defaults(mock_text):
    mock_text.return_value.ask.side_effect = ["staging", "4", "2"]
    prompt_overrides()
    # The three calls should use these defaults in order.
    expected_defaults = ["staging", "4", "2"]
    actual_defaults = [call.kwargs.get("default") for call in mock_text.call_args_list]
    assert actual_defaults == expected_defaults
