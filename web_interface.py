from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Body

from database_manager import DatabaseManager
from scan_tasks import scan_queue

app = FastAPI(title="KZ Monitor", version="2.0")

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

db = DatabaseManager()


# =========== Одна страница ===========
@app.get("/", response_class=HTMLResponse)
async def main_page(request: Request):
    return templates.TemplateResponse("main.html", {"request": request})


# =========== API ===========
@app.get("/api/stats")
async def api_stats():
    return db.get_channel_stats()


@app.get("/api/channels")
async def api_channels(type: str | None = None, limit: int | None = None):
    if limit:
        return db.get_suspicious_channels(limit=limit)
    return db.get_channels_by_type(type)


@app.get("/api/messages")
async def api_messages(channel: str | None = None):
    return db.get_suspicious_messages(channel_username=channel)


@app.post("/api/scan")
async def api_scan(data: dict = Body(...)):
    ch = data.get("channel", "").strip()
    if ch.startswith("http"):
        ch = ch.split("/")[-1]
    if ch.startswith("@"):
        ch = ch[1:]

    scan_queue.put(ch)
    return {"status": f"Сканирование @{ch} добавлено в очередь"}
