"""Pydantic models for the Cortex Autopilot.

These models flow between the API layer, the agent, and the context store.
They are deliberately serializable (model_dump_json) so they can be embedded
in LLM prompts, persisted to SQLite/Postgres, and returned to API callers.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


TriggerType = Literal["manual", "webhook", "auto_detect", "scheduled"]
TaskStatus = Literal["pending", "running", "completed", "blocked", "failed"]
Complexity = Literal["simple", "complex"]
Verdict = Literal["pass", "warn", "block", "upgrade_required"]


class AutopilotTask(BaseModel):
    """A single unit of work processed by the Autopilot agent."""

    task_id: str = Field(default_factory=lambda: str(uuid4()))
    trigger_type: TriggerType = "manual"
    asset_urn: str
    connector: str = "datahub"
    change: Dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    complexity: Optional[Complexity] = None
    verdict: Optional[Verdict] = None
    status: TaskStatus = "pending"
    result: Dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    steps: List["AgentStep"] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


class AgentStep(BaseModel):
    """One iteration of the agent's reasoning loop."""

    step_index: int
    thought: str = ""
    tool_name: Optional[str] = None
    tool_args: Dict[str, Any] = Field(default_factory=dict)
    tool_result: str = ""
    observation: str = ""


class ContextDocument(BaseModel):
    """A retrieved RAG context entry. Returned by the context store."""

    id: str
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    similarity: float = 0.0


class AutopilotStatus(BaseModel):
    """Snapshot of the autopilot's runtime health."""

    enabled: bool
    running: bool
    tier: str
    trial_active: bool
    poll_interval_seconds: int
    registered_assets: int = 0
    total_tasks: int = 0
    recent_tasks: List[AutopilotTask] = Field(default_factory=list)
    last_observation_at: Optional[datetime] = None


AutopilotTask.model_rebuild()
