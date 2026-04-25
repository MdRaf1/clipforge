import os
import shutil
from fastapi import APIRouter, HTTPException, UploadFile, File
from config import FOOTAGE_DIR
from db.queries.footage import add_footage, list_footage

router = APIRouter()

ALLOWED_EXTENSIONS = {".mp4", ".mkv"}


@router.post("/api/footage")
async def upload_footage(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only MP4/MKV files are supported")

    dest_path = os.path.join(FOOTAGE_DIR, file.filename)
    # Avoid overwrite by appending a suffix if needed
    if os.path.exists(dest_path):
        base, ext = os.path.splitext(file.filename)
        counter = 1
        while os.path.exists(dest_path):
            dest_path = os.path.join(FOOTAGE_DIR, f"{base}_{counter}{ext}")
            counter += 1

    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    footage_id = add_footage(
        filename=os.path.basename(dest_path),
        path=dest_path,
    )
    return {"footage_id": footage_id, "filename": os.path.basename(dest_path)}


@router.get("/api/footage")
async def get_footage():
    return list_footage()
