"""Slack notification helper - posts a message to an incoming webhook."""
from typing import Any, Dict
import httpx


def post_slack(webhook_url: str, message: Dict[str, Any]) -> None:
    """POST a JSON message to a Slack incoming webhook.

    Raises RuntimeError on non-2xx response. Slack typically returns
    'ok' as the text body on success.
    """
    if not webhook_url:
        return

    resp = httpx.post(webhook_url, json=message, timeout=10.0)
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Slack webhook returned {resp.status_code}: {resp.text[:200]}"
        )
