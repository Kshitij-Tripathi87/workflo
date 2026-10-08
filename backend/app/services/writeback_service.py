"""Write-back service facade.

Delegates to the synchronous JSONL writer for the mock/single-process case.
The DataHub-native writeback lives in datahub_writeback.py and is used by the
asynchronous future-search / demo paths when a real DataHub is configured.
"""

from typing import Optional

from app.models.impact import ImpactReport
from app.models.recommendation import Recommendation
from app.models.artifact import ArtifactDraft
from app.models.writeback import WritebackRecord
from app.connectors.datahub.writeback import WritebackServiceSync


# Back-compat alias used by existing API routers
class WritebackService(WritebackServiceSync):
    """Alias for WritebackServiceSync - kept for backwards compatibility."""


# Singleton instance
writeback_service = WritebackServiceSync()
