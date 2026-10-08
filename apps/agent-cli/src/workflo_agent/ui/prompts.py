"""Interactive prompts for the goal-based test flow."""

import questionary

GOAL_CHOICES = {
    "smoke": {
        "label": "Smoke tests  -  Quick health check (2 min)",
        "markers": ["smoke"],
    },
    "security": {
        "label": "Security / Tenant Isolation  -  Cross-tenant access control (5 min)",
        "markers": ["security"],
    },
    "integration": {
        "label": "Integration  -  API + UI flows (8 min)",
        "markers": ["integration"],
    },
    "mobile": {
        "label": "Mobile  -  Responsive / device emulation (6 min)",
        "markers": ["mobile"],
    },
    "regression": {
        "label": "Full Regression  -  Everything (25 min)",
        "markers": ["regression"],
    },
    "custom": {
        "label": "Custom  -  Select markers/files manually",
        "markers": [],
    },
}


def prompt_goal() -> str:
    choices = [questionary.Choice(title=v["label"], value=k) for k, v in GOAL_CHOICES.items()]
    answer = questionary.select("What would you like to test?", choices=choices).ask()
    return answer or "smoke"


def prompt_execution_mode() -> str:
    answer = questionary.select(
        "Execution mode:",
        choices=[
            questionary.Choice(title="Cloud (default)  -  Runs on Tenant Shield workers, streams logs", value="cloud"),
            questionary.Choice(title="Local  -  Runs on this machine, no cloud dependency", value="local"),
        ],
    ).ask()
    return answer or "cloud"


def prompt_overrides() -> dict:
    test_env = questionary.text("TEST_ENV", default="staging").ask()
    parallelism = questionary.text("Parallelism", default="4").ask()
    retries = questionary.text("Retries", default="2").ask()
    return {"TEST_ENV": test_env, "PARALLELISM": parallelism, "RETRIES": retries}
