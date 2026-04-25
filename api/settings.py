from fastapi import APIRouter
from db.queries.settings import get_all_settings, set_setting

router = APIRouter()


@router.get("/api/settings")
async def get_settings():
    return get_all_settings()


@router.put("/api/settings")
async def update_settings(updates: dict[str, str]):
    for key, value in updates.items():
        set_setting(key, value)
    return get_all_settings()
