"""Phase 47, steps 47.1-47.15 — platform settings service.

Reads/writes runtime-overridable settings backed by ``platform_settings``,
with defaults sourced from ``AppSettings``. The settings page groups these into
profile / scan schedule / risk filters / breakeven / earnings-IV / manual
option / rejection / checklist / AI provider / UI / memory sections.

Safe-default invariant: ``allow_stock_only_when_options_missing`` defaults to
True and stays True unless the user explicitly changes it, so missing option
data never blocks stock-only research.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.core.config import AppSettings, get_settings
from app.governance.settings_models import PlatformSetting

# The runtime-overridable settings and their AppSettings source attribute.
# (key -> (config_attr, value_type)). Booleans/ints/floats are coerced.
SETTING_SPECS: dict[str, tuple[str, str]] = {
    # Profile / schedule
    "default_strategy_profile": ("default_strategy_profile", "str"),
    "market_data_refresh_minutes": ("market_data_refresh_minutes", "int"),
    "news_refresh_minutes": ("news_refresh_minutes", "int"),
    "iv_risk_refresh_minutes": ("iv_risk_refresh_minutes", "int"),
    # Risk filters / breakeven / option
    "option_max_spread_percent": ("option_max_spread_percent", "float"),
    "option_min_open_interest": ("option_min_open_interest", "int"),
    "option_max_breakeven_distance_percent": (
        "option_max_breakeven_distance_percent",
        "float",
    ),
    # Earnings / IV
    "event_analysis_min_importance": ("event_analysis_min_importance", "str"),
    # Manual option behavior (Phase 47.8)
    "manual_option_input_enabled": ("manual_option_input_enabled", "bool"),
    "option_text_ai_reader_enabled": ("option_text_ai_reader_enabled", "bool"),
    "strict_option_parser_mode": ("strict_option_parser_mode", "bool"),
    "allow_stock_only_when_options_missing": (
        "allow_stock_only_when_options_missing",
        "bool",
    ),
    # AI provider / UI display
    "active_ai_provider": ("active_ai_provider", "str"),
    "fallback_ai_provider": ("fallback_ai_provider", "str"),
}


def _coerce(value: str | None, value_type: str) -> Any:
    if value is None:
        return None
    if value_type == "bool":
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    if value_type == "int":
        try:
            return int(value)
        except ValueError:
            return None
    if value_type == "float":
        try:
            return float(value)
        except ValueError:
            return None
    return value


class SettingsService:
    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or get_settings()

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    def _default(self, key: str) -> Any:
        attr, _ = SETTING_SPECS[key]
        return getattr(self.settings, attr, None)

    def get_all(self, db: Session) -> dict[str, Any]:
        """Effective settings: DB override when present, else config default."""
        self.ensure_tables(db)
        overrides = {
            row.key: _coerce(row.value, row.value_type)
            for row in db.query(PlatformSetting).all()
        }
        effective: dict[str, Any] = {}
        for key, (_attr, value_type) in SETTING_SPECS.items():
            if key in overrides and overrides[key] is not None:
                effective[key] = overrides[key]
            else:
                effective[key] = self._default(key)
            effective.setdefault(f"__type__{key}", value_type)
        # Strip the helper type markers for the public view.
        return {k: v for k, v in effective.items() if not k.startswith("__type__")}

    def get(self, db: Session, key: str) -> Any:
        if key not in SETTING_SPECS:
            raise ValueError(f"unknown setting '{key}'")
        return self.get_all(db)[key]

    def set(self, db: Session, key: str, value: Any) -> Any:
        self.ensure_tables(db)
        if key not in SETTING_SPECS:
            raise ValueError(f"unknown setting '{key}'")
        value_type = SETTING_SPECS[key][1]
        row = db.query(PlatformSetting).filter(PlatformSetting.key == key).one_or_none()
        if row is None:
            row = PlatformSetting(key=key, value=str(value), value_type=value_type)
            db.add(row)
        else:
            row.value = str(value)
            row.value_type = value_type
        db.commit()
        return _coerce(str(value), value_type)

    def set_many(self, db: Session, values: dict[str, Any]) -> dict[str, Any]:
        for key, value in values.items():
            self.set(db, key, value)
        return self.get_all(db)

    def reset(self, db: Session, *, key: str | None = None) -> dict[str, Any]:
        """Reset one setting (or all) back to config defaults."""
        self.ensure_tables(db)
        if key is not None:
            if key not in SETTING_SPECS:
                raise ValueError(f"unknown setting '{key}'")
            db.query(PlatformSetting).filter(PlatformSetting.key == key).delete()
        else:
            db.query(PlatformSetting).delete()
        db.commit()
        return self.get_all(db)


__all__ = ["SETTING_SPECS", "SettingsService"]
