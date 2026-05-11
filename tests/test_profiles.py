import pytest

from app.profiles.default_profiles import (
    get_aggressive_research,
    get_balanced_research_default,
    get_conservative_research,
    get_custom_profile_template,
    get_default_profiles,
)
from app.profiles.profile_models import StrategyProfile


def test_balanced_research_default_loads() -> None:
    profile = get_balanced_research_default()

    assert profile.profile_name == "Balanced Research Default"
    assert profile.profile_version == "balanced_research_default_1.0"
    assert profile.stock_thesis_horizon_min_trading_days == 10
    assert profile.stock_thesis_horizon_max_trading_days == 25
    assert profile.option_dte_min == 45
    assert profile.option_dte_max == 90
    assert profile.premium_min_usd == 500
    assert profile.premium_max_usd == 1000
    assert profile.minimum_risk_reward == 2.0
    assert profile.reject_if_target_below_breakeven is True
    assert profile.minimum_target_breakeven_margin_percent == 3
    assert profile.iv_warning_threshold == 70
    assert profile.iv_reject_threshold == 85
    assert profile.earnings_risk_window_days == 7
    assert profile.hard_filters_can_be_bypassed is False


def test_conservative_research_is_more_strict_than_balanced() -> None:
    balanced = get_balanced_research_default()
    conservative = get_conservative_research()

    assert conservative.minimum_risk_reward > balanced.minimum_risk_reward
    assert (
        conservative.minimum_target_breakeven_margin_percent
        > balanced.minimum_target_breakeven_margin_percent
    )
    assert conservative.iv_warning_threshold < balanced.iv_warning_threshold
    assert conservative.hard_filters_can_be_bypassed is False


def test_aggressive_research_does_not_bypass_hard_filters() -> None:
    aggressive = get_aggressive_research()

    assert aggressive.profile_name == "Aggressive Research"
    assert aggressive.hard_filters_can_be_bypassed is False
    assert aggressive.reject_if_target_below_breakeven is True


def test_custom_profile_template_loads() -> None:
    custom = get_custom_profile_template()

    assert custom.profile_name == "Custom"
    assert custom.profile_version == "custom_1.0"
    assert custom.hard_filters_can_be_bypassed is False


def test_default_profiles_include_all_initial_profiles() -> None:
    profiles = get_default_profiles()
    profile_names = {profile.profile_name for profile in profiles}

    assert "Balanced Research Default" in profile_names
    assert "Conservative Research" in profile_names
    assert "Aggressive Research" in profile_names
    assert "Custom" in profile_names


def test_profile_validation_rejects_hard_filter_bypass() -> None:
    balanced = get_balanced_research_default()
    invalid_payload = balanced.model_dump()
    invalid_payload["hard_filters_can_be_bypassed"] = True

    with pytest.raises(ValueError):
        StrategyProfile(**invalid_payload)