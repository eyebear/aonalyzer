from fastapi import APIRouter, HTTPException

from app.profiles.profile_manager import profile_manager
from app.profiles.profile_models import ActiveProfileResponse, ProfileListResponse, StrategyProfile

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/profile", response_model=ActiveProfileResponse)
def get_active_profile() -> ActiveProfileResponse:
    profile = profile_manager.get_active_profile()

    return ActiveProfileResponse(
        active_profile_name=profile.profile_name,
        active_profile_version=profile.profile_version,
        profile=profile,
    )


@router.get("/profiles", response_model=ProfileListResponse)
def list_profiles() -> ProfileListResponse:
    return ProfileListResponse(profiles=profile_manager.list_profiles())


@router.post("/profile", response_model=ActiveProfileResponse)
def save_custom_profile(profile: StrategyProfile) -> ActiveProfileResponse:
    try:
        saved_profile = profile_manager.save_custom_profile(profile)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ActiveProfileResponse(
        active_profile_name=saved_profile.profile_name,
        active_profile_version=saved_profile.profile_version,
        profile=saved_profile,
    )