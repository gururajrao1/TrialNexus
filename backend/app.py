"""TrialNexus FastAPI entrypoint. Run from the project root:

uvicorn backend.app:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import FRONTEND_DIR
from backend.routes import core, product, tier

app = FastAPI(title="TrialNexus Multi-Agent OS API")


@app.get("/", include_in_schema=False)
def serve_ui() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
app.include_router(core.router)
app.include_router(product.router)
app.include_router(tier.router)
