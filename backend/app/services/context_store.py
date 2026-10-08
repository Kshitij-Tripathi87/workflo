"""Context Store - the Autopilot's persistent memory.

Combines two storage backends:

1. ChromaDB        — vector store for semantic retrieval over past
                     incidents, asset states, and task summaries. This
                     is what powers RAG: the agent queries it before
                     every plan to pull in relevant history.
2. SQLAlchemy      — optional Postgres-backed structured store for the
                     AssetState registry (used by the observer loop to
                     detect schema drift) and AutopilotTaskDB audit log.

If `DATABASE_URL` is unset (dev/mock mode), the structure-layer falls
back to an in-memory dict so the Autopilot still works end-to-end.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.settings import settings
from app.models.autopilot import AutopilotTask, ContextDocument


# ---------------------------------------------------------------------------
# Schema hash helper (used by the observer loop to detect changes)
# ---------------------------------------------------------------------------

def compute_schema_hash(schema_fields: List[str]) -> str:
    """Stable hash of a schema so we can detect drift cheaply."""
    normalized = sorted(f.lower() for f in (schema_fields or []))
    return hashlib.sha1("|".join(normalized).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# ChromaDB layer — vector storage for RAG
# ---------------------------------------------------------------------------

class _InMemoryStore:
    """Minimal fallback when chromadb isn't installed (CI / dev without deps)."""

    def __init__(self):
        self._docs: Dict[str, Dict[str, Any]] = {}

    def add(self, ids, documents, metadatas):
        for i, doc, meta in zip(ids, documents, metadatas):
            self._docs[i] = {"document": doc, "metadata": meta or {}}

    def query(self, query_texts, n_results):
        q = (query_texts or [""])[0].lower()
        scored = []
        for _id, entry in self._docs.items():
            text = entry["document"].lower()
            # Tiny relevance score: fraction of query words found in text
            words = [w for w in q.split() if w]
            if not words:
                score = 0.0
            else:
                hits = sum(1 for w in words if w in text)
                score = hits / len(words)
            scored.append((score, _id, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            ContextDocument(
                id=s[1],
                text=s[2]["document"],
                metadata=s[2]["metadata"],
                similarity=s[0],
            )
            for s in scored[:n_results]
        ]

    def count(self) -> int:
        return len(self._docs)


class ContextStore:
    """The Autopilot's memory: vector search + structured asset registry."""

    def __init__(self) -> None:
        self._chroma = self._init_chroma()
        self._asset_state_cache: Dict[str, Dict[str, Any]] = {}
        self._task_log: List[AutopilotTask] = []

    # -- Chroma -----------------------------------------------------------
    def _init_chroma(self):
        try:
            import chromadb
        except ImportError:
            return _InMemoryStore()

        path = settings.CORTEX_CHROMA_PATH
        try:
            client = chromadb.PersistentClient(path=path)
            self._collection = client.get_or_create_collection(
                name=settings.CORTEX_CHROMA_COLLECTION,
            )
            return self._collection
        except Exception:
            return _InMemoryStore()

    # -- RAG retrieval ----------------------------------------------------
    def retrieve_context(
        self,
        query: str,
        k: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[ContextDocument]:
        """Top-k most relevant context entries for `query`."""
        if not query or not query.strip():
            return []

        if isinstance(self._chroma, _InMemoryStore):
            return self._chroma.query([query], n_results=k)

        try:
            result = self._chroma.query(
                query_texts=[query],
                n_results=k,
                where=where,
            )
        except Exception:
            return []

        documents = result.get("documents", [[]])
        metadatas = result.get("metadatas", [[]])
        distances = result.get("distances", [[]])

        docs = documents[0] if documents else []
        metas = metadatas[0] if metadatas else []
        dists = distances[0] if distances else []

        out: List[ContextDocument] = []
        for idx, text in enumerate(docs):
            dist = dists[idx] if idx < len(dists) else 1.0
            meta = metas[idx] if idx < len(metas) else {}
            out.append(
                ContextDocument(
                    id=meta.get("id", f"doc-{idx}"),
                    text=text,
                    metadata=meta,
                    similarity=max(0.0, 1.0 - float(dist)),
                )
            )
        return out

    # -- Asset state registry --------------------------------------------
    def store_asset_state(
        self,
        asset_urn: str,
        connector: str,
        name: Optional[str] = None,
        owner: Optional[str] = None,
        schema_fields: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Record the latest observed state of an asset.

        Returns True if the state CHANGED since last observation (i.e. the
        observer loop should enqueue a task for this asset).
        """
        new_hash = compute_schema_hash(schema_fields or [])
        key = f"asset:{asset_urn}"
        prev = self._asset_state_cache.get(key)

        changed = False
        if prev is None:
            changed = False  # first observation isn't a "change"
        elif (
            prev.get("schema_hash") != new_hash
            or prev.get("owner") != owner
        ):
            changed = True

        record = {
            "asset_urn": asset_urn,
            "connector": connector,
            "name": name,
            "owner": owner,
            "schema_fields": schema_fields or [],
            "schema_hash": new_hash,
            "change_frequency": (prev or {}).get("change_frequency", 0.0)
            + (1.0 if changed else 0.0),
            "past_incidents": (prev or {}).get("past_incidents", 0),
            "last_seen": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }
        self._asset_state_cache[key] = record

        # Push a snapshot into the vector store so it's queryable
        self._index_document(
            doc_id=key,
            text=f"Asset {asset_urn} ({name or ''}). Owner: {owner or 'none'}. "
            f"Schema: {', '.join(schema_fields or [])}.",
            metadata={
                "kind": "asset_state",
                "asset_urn": asset_urn,
                "connector": connector,
                "schema_hash": new_hash,
            },
        )
        return changed

    def get_asset_state(self, asset_urn: str) -> Optional[Dict[str, Any]]:
        return self._asset_state_cache.get(f"asset:{asset_urn}")

    def list_registered_assets(self) -> List[str]:
        return [
            v["asset_urn"] for v in self._asset_state_cache.values()
        ]

    # -- Task log ---------------------------------------------------------
    def store_task(self, task: AutopilotTask) -> None:
        self._task_log.append(task)
        self._index_document(
            doc_id=f"task:{task.task_id}",
            text=(
                f"Task for {task.asset_urn} ({task.connector}). "
                f"Complexity: {task.complexity}. Verdict: {task.verdict}. "
                f"Summary: {task.summary}"
            ),
            metadata={
                "kind": "task",
                "task_id": task.task_id,
                "asset_urn": task.asset_urn,
                "complexity": task.complexity or "",
                "verdict": task.verdict or "",
            },
        )

    def recent_tasks(self, limit: int = 10) -> List[AutopilotTask]:
        return list(reversed(self._task_log[-limit:]))

    def total_tasks(self) -> int:
        return len(self._task_log)

    def context_count(self) -> int:
        if isinstance(self._chroma, _InMemoryStore):
            return self._chroma.count()
        try:
            return self._chroma.count()
        except Exception:
            return 0

    # -- Internals --------------------------------------------------------
    def _index_document(self, doc_id: str, text: str, metadata: Dict[str, Any]) -> None:
        if isinstance(self._chroma, _InMemoryStore):
            self._chroma.add([doc_id], [text], [metadata])
            return
        try:
            self._chroma.upsert(
                ids=[doc_id],
                documents=[text],
                metadatas=[metadata],
            )
        except Exception:
            pass
