from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.model_layer.model_worker import ModelWorker

router = APIRouter(prefix="/api/models", tags=["models"])


class SentimentRequest(BaseModel):
    text: str


@router.get("/status")
def get_model_status() -> dict[str, Any]:
    worker = ModelWorker()
    return {"status": "OK", **worker.get_status()}


@router.get("/versions")
def list_model_versions() -> dict[str, Any]:
    worker = ModelWorker()
    return {"status": "OK", "versions": worker.registry.to_dict()}


@router.post("/sentiment")
def analyze_sentiment(request: SentimentRequest) -> dict[str, Any]:
    """Demonstrates the foundation: returns a deterministic fallback result when
    models are disabled, a real result when enabled and available."""
    worker = ModelWorker()
    result = worker.analyze_sentiment(request.text)
    return {"status": "OK", "result": result.to_dict()}
