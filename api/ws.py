import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from db.queries.jobs import get_job

router = APIRouter()

# In-memory queues keyed by job_id
_queues: dict[int, list[asyncio.Queue]] = {}


def push_event(job_id: int, event: dict) -> None:
    for q in _queues.get(job_id, []):
        q.put_nowait(event)


@router.websocket("/ws/jobs/{job_id}")
async def ws_jobs(websocket: WebSocket, job_id: int):
    await websocket.accept()

    # Push current state immediately to handle race condition
    job = get_job(job_id)
    if job:
        await websocket.send_text(json.dumps({
            "type": "state_sync",
            "steps": job["steps"],
        }))

    # Register a queue for this connection
    q: asyncio.Queue = asyncio.Queue()
    _queues.setdefault(job_id, []).append(q)

    try:
        while True:
            event = await q.get()
            await websocket.send_text(json.dumps(event))
    except WebSocketDisconnect:
        pass
    finally:
        _queues[job_id].remove(q)
        if not _queues[job_id]:
            del _queues[job_id]
