"""Phase 42, steps 42.4-42.10 — vector memory ingest + search.

Embeds case memory, user feedback (overrides), rejected cases, manual option
snapshots, AI summaries, and action suggestions into ``memory_embeddings``, and
provides cosine-similarity search. Vector memory is *supporting context only*:
it influences confidence, warnings, and explanations, never the deterministic
data-sufficiency / hard-filter / final-label gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.memory.case_memory_models import CaseMemory
from app.memory.embedding_service import MemoryEmbeddingService, cosine_similarity
from app.memory.memory_embedding_models import (
    EMBED_ACTION_SUGGESTION,
    EMBED_CASE_MEMORY,
    EMBED_MANUAL_OPTION,
    EMBED_REJECTED_CASE,
    EMBED_USER_FEEDBACK,
    MemoryEmbedding,
    try_enable_pgvector,
)


@dataclass
class IngestResult:
    embedded: int = 0
    skipped: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"embedded": self.embedded, "skipped": self.skipped}


class VectorSearchService:
    def __init__(self, embedding_service: MemoryEmbeddingService | None = None) -> None:
        self.embedding_service = embedding_service or MemoryEmbeddingService()

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    # ----------------------------------------------------------------- ingest

    def ingest_all(self, db: Session, *, limit: int = 500) -> IngestResult:
        self.ensure_tables(db)
        try_enable_pgvector(db)  # best-effort; portable path is JSON cosine
        result = IngestResult()
        self._ingest_case_memory(db, result, limit)
        self._ingest_rejected_cases(db, result, limit)
        self._ingest_overrides(db, result, limit)
        self._ingest_manual_options(db, result, limit)
        self._ingest_action_suggestions(db, result, limit)
        db.commit()
        return result

    def _ingest_case_memory(self, db: Session, result: IngestResult, limit: int) -> None:
        for row in db.query(CaseMemory).limit(limit).all():
            text = f"{row.symbol} {row.case_type} {row.outcome_type} {row.lesson_summary or ''}"
            self._upsert(db, EMBED_CASE_MEMORY, row.id, row.symbol, text, result)

    def _ingest_rejected_cases(self, db: Session, result: IngestResult, limit: int) -> None:
        try:
            from app.rejection.rejection_models import RejectedCandidate

            rows = db.query(RejectedCandidate).limit(limit).all()
        except Exception:
            return
        for row in rows:
            text = (
                f"{row.symbol} {row.rejection_category} {row.summary or ''}"
            )
            self._upsert(db, EMBED_REJECTED_CASE, row.id, row.symbol, text, result)

    def _ingest_overrides(self, db: Session, result: IngestResult, limit: int) -> None:
        try:
            from app.user_actions.user_action_models import UserOverride

            rows = db.query(UserOverride).limit(limit).all()
        except Exception:
            return
        for row in rows:
            text = f"{row.symbol} {row.override_type} {row.system_suggestion_label or ''}"
            self._upsert(db, EMBED_USER_FEEDBACK, row.id, row.symbol, text, result)

    def _ingest_manual_options(self, db: Session, result: IngestResult, limit: int) -> None:
        try:
            from app.options.manual_option_input_service import ManualOptionInputService

            snaps = ManualOptionInputService().list_manual_snapshots(db=db, limit=limit)
        except Exception:
            return
        for snap in snaps:
            d = snap.to_dict()
            text = (
                f"{d.get('symbol')} option {d.get('option_type')} {d.get('strike')} "
                f"{d.get('ai_summary') or ''}"
            )
            self._upsert(db, EMBED_MANUAL_OPTION, d.get("id"), d.get("symbol"), text, result)

    def _ingest_action_suggestions(self, db: Session, result: IngestResult, limit: int) -> None:
        try:
            from app.action.action_models import ActionSuggestion

            rows = db.query(ActionSuggestion).limit(limit).all()
        except Exception:
            return
        for row in rows:
            text = (
                f"{row.symbol} {row.final_action_label} {row.suggested_action_summary or ''}"
            )
            self._upsert(db, EMBED_ACTION_SUGGESTION, row.id, row.symbol, text, result)

    def _upsert(
        self,
        db: Session,
        source_type: str,
        source_id: int | None,
        symbol: str | None,
        text: str,
        result: IngestResult,
    ) -> None:
        existing = (
            db.query(MemoryEmbedding)
            .filter(MemoryEmbedding.source_type == source_type)
            .filter(MemoryEmbedding.source_id == source_id)
            .one_or_none()
        )
        vector, model_name = self.embedding_service.embed_text(text)
        if existing is not None:
            existing.content_text = text
            existing.embedding_json = vector
            existing.dim = len(vector)
            existing.model_name = model_name
            result.skipped += 1
            return
        db.add(
            MemoryEmbedding(
                source_type=source_type,
                source_id=source_id,
                symbol=symbol,
                content_text=text,
                embedding_json=vector,
                dim=len(vector),
                model_name=model_name,
            )
        )
        result.embedded += 1

    # ----------------------------------------------------------------- search

    def search(
        self,
        db: Session,
        *,
        query_text: str,
        limit: int = 5,
        source_type: str | None = None,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        self.ensure_tables(db)
        query_vec, _ = self.embedding_service.embed_text(query_text)

        q = db.query(MemoryEmbedding)
        if source_type is not None:
            q = q.filter(MemoryEmbedding.source_type == source_type)
        if symbol is not None:
            q = q.filter(MemoryEmbedding.symbol == symbol.strip().upper())
        rows = q.all()

        scored = [
            (cosine_similarity(query_vec, row.embedding_json or []), row) for row in rows
        ]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            {
                "source_type": row.source_type,
                "source_id": row.source_id,
                "symbol": row.symbol,
                "content_text": row.content_text,
                "similarity": round(score, 6),
            }
            for score, row in scored[:limit]
        ]


__all__ = ["IngestResult", "VectorSearchService"]
