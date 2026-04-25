from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from db.models import init_db
from db.connection import get_db
from api import jobs, footage, settings, series, history, ws
import os


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Init DB and seed defaults
    init_db()
    # Startup interrupt sweep: mark any in-progress jobs as interrupted
    with get_db() as conn:
        conn.execute("UPDATE jobs SET status='interrupted' WHERE status='in_progress'")
    yield


app = FastAPI(title="ClipForge", lifespan=lifespan)

app.include_router(jobs.router)
app.include_router(footage.router)
app.include_router(settings.router)
app.include_router(series.router)
app.include_router(history.router)
app.include_router(ws.router)

# Serve frontend static files if the directory exists
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
