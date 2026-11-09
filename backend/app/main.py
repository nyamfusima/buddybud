import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import admin, auth, coach, insights, me, team
from app.core.config import get_settings
from app.core.llm import provider_info

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
settings = get_settings()
if settings.env == "prod" and settings.secret_key.startswith("change-me"):
    raise RuntimeError("Set SECRET_KEY to a long random value before running in production.")

app = FastAPI(title=settings.app_name, version="0.3.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth.router, me.router, team.router, insights.router, coach.router, admin.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True, "env": settings.env, "llm": provider_info()}


# Optional: serve the built React app from the same service (one deploy, no CORS).
if settings.serve_frontend_dir and Path(settings.serve_frontend_dir).is_dir():
    dist = Path(settings.serve_frontend_dir)
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        candidate = dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")
