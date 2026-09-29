"""Mission state — the structured working memory the model actually reads.

The planner must never shovel raw history into the prompt forever: tokens
are the unit of cost. MissionState compresses the governed observations
into the small, stable structure the model needs to make the NEXT decision
well:

    mission            — what the user asked for (bounded, redacted)
    endpoints          — path -> latest status (the map of what's known)
    failures           — compact failure lines (the open questions)
    tools_used/calls   — budget context
    done               — settable stop signal

Deterministic: built from observations without any model call. The planner
renders it as a compact prompt section; raw observation tails still go
through the data fences for detail.

All strings derived from observations are capped — this block must never
become a second covert exfiltration channel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

MAX_ENDPOINTS = 24
MAX_FAILURE_LINES = 12
MAX_FIELD_CHARS = 200


@dataclass
class MissionState:
    mission: Optional[str] = None
    endpoints: dict[str, str] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    observations_total: int = 0
    tool_calls: int = 0
    denied_attempts: int = 0
    done: bool = False

    # ------------------------------------------------------------------ build

    @classmethod
    def from_observations(cls, observations: list[dict],
                          mission: Optional[str] = None,
                          tool_calls: int = 0,
                          denied_attempts: int = 0) -> "MissionState":
        state = cls(mission=(mission or None), tool_calls=tool_calls,
                    denied_attempts=denied_attempts,
                    observations_total=len(observations))
        for obs in observations:
            state.absorb(obs)
        return state

    def absorb(self, observation: dict) -> None:
        """Fold one governed observation into the state."""
        if not isinstance(observation, dict):
            return
        desc = str(observation.get("description", ""))[:MAX_FIELD_CHARS]
        detail = str(observation.get("detail", ""))[:MAX_FIELD_CHARS]
        tool = observation.get("tool")
        if tool in ("http_get", "http_post"):
            endpoint = _endpoint_of(observation)
            if endpoint:
                self.endpoints[endpoint] = detail or ("ok" if observation.get("ok") else "?")
        if observation.get("denied") or observation.get("ok") is False:
            line = f"{desc}: {detail}".strip(": ")
            if line and line not in self.failures:
                self.failures.append(line)

    # ------------------------------------------------------------------ render

    def prompt_block(self) -> str:
        """Compact state section for the planner prompt (bounded lines)."""
        lines = ["State:"]
        if self.mission:
            lines.append(f"  mission: {self.mission}")
        lines.append(
            f"  observations: {self.observations_total} total, "
            f"{self.tool_calls} tool calls, {self.denied_attempts} denied"
        )
        if self.endpoints:
            lines.append("  endpoints:")
            for path, status in list(self.endpoints.items())[:MAX_ENDPOINTS]:
                lines.append(f"    {path} -> {status}")
        if self.failures:
            lines.append("  open failures:")
            for failure in self.failures[:MAX_FAILURE_LINES]:
                lines.append(f"    - {failure}")
        return "\n".join(lines)


def _endpoint_of(observation: dict) -> Optional[str]:
    """Extract a compact 'METHOD /path' key from an HTTP observation."""
    desc = str(observation.get("description", ""))
    detail = str(observation.get("detail", ""))
    method = "POST" if observation.get("tool") == "http_post" else "GET"
    # The agent writes descriptions like "GET /health" or the detail like
    # "HTTP 500". The args URL itself is not in the observation schema, so
    # the endpoint is recovered from the description's first token pair.
    parts = desc.split()
    for i, part in enumerate(parts):
        if part.startswith("/"):
            method = parts[i - 1].upper() if i > 0 and parts[i - 1].upper() in ("GET", "POST") else method
            return f"{method} {part.split('?')[0][:80]}"
    return None


def recent_observations_block(observations: list[dict], keep: int = 20) -> list[dict]:
    """Bounded recent-observation slice (raw detail for the data fence)."""
    return observations[-keep:] if len(observations) > keep else list(observations)
