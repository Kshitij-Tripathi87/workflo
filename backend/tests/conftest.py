import os
import tempfile


os.environ.setdefault("AUTH_REQUIRED", "false")
os.environ.setdefault("USE_MOCK_DATAHUB", "true")

# The JSONL write-back mirror must never touch the repository's tracked data
# files (backend/data/writeback.jsonl is committed, and every write-back test
# used to append to it, leaving the worktree dirty). Point the mirror at a
# per-run temporary directory instead. This is set BEFORE app modules are
# imported because app.core.settings builds its singleton at import time.
# tests/test_security.py::test_writeback_mirror_stays_out_of_the_repo guards it.
os.environ["WRITEBACK_DIR"] = tempfile.mkdtemp(prefix="workflo-test-writeback-")
