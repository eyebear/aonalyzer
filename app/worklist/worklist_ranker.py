"""Phase 27, step 27.4 — worklist item ranker.

Deterministic ordering of the day's tasks so the most urgent research work
surfaces first. Pure function over ``WorklistItemDraft`` objects: sorts by
priority, then by worklist-type ordering, then symbol (stable), and assigns a
1-based ``rank`` to each item in place.
"""

from __future__ import annotations

from app.worklist.worklist_generator import WorklistItemDraft
from app.worklist.worklist_types import priority_rank, type_rank


def rank_items(drafts: list[WorklistItemDraft]) -> list[WorklistItemDraft]:
    """Return ``drafts`` sorted and with ``rank`` assigned (1-based).

    Ordering key: (priority_rank, type_rank, symbol). Lower sorts first /
    higher urgency. The sort is stable so equal keys preserve insertion
    order (which mirrors generator source order).
    """
    ordered = sorted(
        drafts,
        key=lambda d: (
            priority_rank(d.priority),
            type_rank(d.worklist_type),
            d.symbol or "",
        ),
    )
    for index, draft in enumerate(ordered, start=1):
        draft.rank = index
    return ordered


__all__ = ["rank_items"]
