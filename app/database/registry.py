"""Central import point that registers every ORM model on ``Base.metadata``.

The project materializes most non-core tables lazily via ``create_all`` (see
``app.common.service_utils.ensure_tables``), so model classes live in per-domain
modules rather than a single file. Importing this module guarantees that *all*
ORM tables are registered on ``Base.metadata``. It is used by Alembic's
``env.py`` so the migration metadata is complete, and is available anywhere the
full schema needs to be created at once.

When a later phase adds a new ORM model module, import it here so the registry
stays authoritative. (Modules that only define dataclasses or persist via raw
SQL -- e.g. ``app.options.manual_option_models`` -- intentionally have no entry.)
"""

from __future__ import annotations

from app.action import action_models  # noqa: F401
from app.ai_analysis import event_analysis_models  # noqa: F401
from app.ai_providers import ai_provider_models  # noqa: F401
from app.data_quality import data_quality_models  # noqa: F401
from app.database import models  # noqa: F401
from app.decision import decision_models  # noqa: F401
from app.database.base import Base
from app.earnings import earnings_models  # noqa: F401
from app.hard_filter import hard_filter_models  # noqa: F401
from app.iv_history import iv_models  # noqa: F401
from app.lifecycle import lifecycle_models  # noqa: F401
from app.market_data import market_data_models  # noqa: F401
from app.market_regime import market_regime_models  # noqa: F401
from app.options import option_candidate_models  # noqa: F401
from app.rejection import rejection_models  # noqa: F401
from app.review import review_models  # noqa: F401
from app.risk_control import do_not_touch_models  # noqa: F401
from app.quant import (
    stock_setup_models,  # noqa: F401
    technical_snapshot_models,  # noqa: F401
)
from app.setup_detection import setup_detection_models  # noqa: F401

__all__ = ["Base"]
