"""TrialNexus FastAPI entrypoint. Run from the project root:

uvicorn backend.app:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.auth import authorized
from backend.config import FRONTEND_DIR
from backend.routes import core, product, tier

app = FastAPI(title="TrialNexus Multi-Agent OS API")


@app.middleware("http")
async def token_guard(request: Request, call_next):
    if not authorized(request.url.path, request.headers.get("authorization")):
        return JSONResponse({"detail": "API token required"}, status_code=401)
    return await call_next(request)


@app.get("/", include_in_schema=False)
def serve_ui() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
app.include_router(core.router)
app.include_router(product.router)
app.include_router(tier.router)
