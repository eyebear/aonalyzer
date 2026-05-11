from app.core.config import get_settings
from app.profiles.default_profiles import get_default_profiles
from app.profiles.profile_models import StrategyProfile


class ProfileManager:
    def __init__(self) -> None:
        self._profiles: dict[str, StrategyProfile] = {
            profile.profile_name: profile for profile in get_default_profiles()
        }

    def list_profiles(self) -> list[StrategyProfile]:
        return list(self._profiles.values())

    def get_profile(self, profile_name: str) -> StrategyProfile:
        if profile_name not in self._profiles:
            raise KeyError(f"Unknown strategy profile: {profile_name}")

        return self._profiles[profile_name]

    def get_active_profile(self) -> StrategyProfile:
        settings = get_settings()
        return self.get_profile(settings.default_strategy_profile)

    def save_custom_profile(self, profile: StrategyProfile) -> StrategyProfile:
        if profile.hard_filters_can_be_bypassed:
            raise ValueError("hard filters cannot be bypassed")

        self._profiles[profile.profile_name] = profile
        return profile


profile_manager = ProfileManager()