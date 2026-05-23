"""Phase 37, step 37.4 — memory retriever integration.

Single place that pulls similar historical cases for the chat. Case memory
(Phase 41) and vector memory (Phase 42) back this; until cases exist it
degrades gracefully to an empty list so the chat honestly reports "no similar
cases" rather than inventing them.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session


def retrieve_similar_cases(
    db: Session, symbol: str | None, *, limit: int = 5
) -> list[dict[str, Any]]:
    if not symbol:
        return []
    try:
        from app.memory.case_memory_models import CaseMemory

        rows = (
            db.query(CaseMemory)
            .filter(CaseMemory.symbol == symbol.strip().upper())
            .order_by(CaseMemory.created_at.desc())
            .limit(limit)
            .all()
        )
    except Exception:
        return []
    return [
        {
            "id": r.id,
            "case_type": r.case_type,
            "outcome_type": r.outcome_type,
            "lesson_summary": r.lesson_summary,
            "option_data_available": r.option_data_available,
        }
        for r in rows
    ]


def retrieve_similar_by_vector(
    db: Session, query_text: str, *, limit: int = 5
) -> list[dict[str, Any]]:
    """Vector-memory backed retrieval (Phase 42). Degrades to [] when absent."""
    try:
        from app.memory.vector_search_service import VectorSearchService

        return VectorSearchService().search(db, query_text=query_text, limit=limit)
    except Exception:
        return []


__all__ = ["retrieve_similar_by_vector", "retrieve_similar_cases"]
