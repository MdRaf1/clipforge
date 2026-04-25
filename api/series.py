from fastapi import APIRouter
from pydantic import BaseModel
from db.queries.series import create_series, list_series

router = APIRouter()


class CreateSeriesRequest(BaseModel):
    name: str


@router.get("/api/series")
async def get_series():
    return list_series()


@router.post("/api/series")
async def post_series(req: CreateSeriesRequest):
    series_id = create_series(req.name)
    return {"series_id": series_id, "name": req.name}
