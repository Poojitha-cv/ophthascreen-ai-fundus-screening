# from __future__ import annotations

# import logging
# from collections.abc import Callable
# from contextlib import asynccontextmanager

# from fastapi import FastAPI, Request
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import JSONResponse
# from PIL import Image
# from sqlalchemy import text
# from sqlalchemy.orm import sessionmaker

# from app import db_models  # noqa: F401  (registers tables)
# from app.core.config import Settings, get_settings
# from app.core.database import Base, make_engine
# from app.modules.auth.router import router as auth_router
# from app.modules.dashboard.router import router as dashboard_router
# from app.modules.imaging.storage import LocalStorage
# from app.modules.inference.engine import load_engine
# from app.modules.inference.protocol import ImageModel
# from app.modules.patients.router import router as patients_router
# from app.modules.reviews.router import router as reviews_router
# from app.modules.screenings.router import router as screenings_router

# log = logging.getLogger("app")

# # Each module contributes one router. Adding a module (e.g. clinical data) = write it + append here.
# API_ROUTERS = [auth_router, patients_router, screenings_router, reviews_router, dashboard_router]


# def create_app(settings: Settings | None = None,
#                engine_loader: Callable[[Settings], ImageModel | None] = load_engine) -> FastAPI:
#     """engine_loader is injectable so tests (or a future remote-inference client) can supply the model."""
#     settings = settings or get_settings()

#     @asynccontextmanager
#     async def lifespan(app: FastAPI):
#         Image.MAX_IMAGE_PIXELS = settings.max_image_pixels
#         db_engine = make_engine(settings.database_url)
#         Base.metadata.create_all(db_engine)  # TODO before production: switch to Alembic migrations
#         app.state.settings = settings
#         app.state.db_engine = db_engine
#         app.state.session_factory = sessionmaker(db_engine, expire_on_commit=True)
#         app.state.storage = LocalStorage(settings.storage_dir)
#         app.state.engine = engine_loader(settings)
#         yield
#         db_engine.dispose()

#     prod = settings.env == "production"
#     app = FastAPI(title="Ophthalmic Screening API (fundus)", version="0.1.0", lifespan=lifespan,
#                   docs_url=None if prod else "/docs", redoc_url=None if prod else "/redoc", openapi_url=None if prod else "/openapi.json")

#     if settings.cors_origins:
#         app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
#                            allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])

#     @app.middleware("http")
#     async def guard_and_headers(request: Request, call_next):
#         # Cheap early rejection of oversized bodies (chunked uploads still need a proxy limit, see README).
#         if request.method in ("POST", "PUT", "PATCH"):
#             try:
#                 declared = int(request.headers.get("content-length", "0") or 0)
#             except ValueError:
#                 declared = 0
#             if declared > 2 * settings.max_upload_bytes + (1 << 20):
#                 return JSONResponse({"detail": "Request body too large"}, status_code=413)
#         response = await call_next(request)
#         response.headers.setdefault("X-Content-Type-Options", "nosniff")
#         if request.url.path.startswith("/api/"):
#             response.headers.setdefault("Cache-Control", "no-store")  # responses contain patient data
#         return response

#     for r in API_ROUTERS:
#         app.include_router(r, prefix="/api/v1")

#     @app.get("/health", tags=["system"])
#     def health(request: Request):
#         db_ok = True
#         try:
#             with request.app.state.db_engine.connect() as c:
#                 c.execute(text("SELECT 1"))
#         except Exception:
#             db_ok = False
#         eng = request.app.state.engine
#         ok = db_ok and eng is not None
#         return JSONResponse({"status": "ok" if ok else "degraded", "database": db_ok, "model_loaded": eng is not None,
#                              "model_tag": eng.info.tag if eng else None}, status_code=200 if db_ok else 503)

#     return app



# # new version with clinical data
from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from PIL import Image
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app import db_models  # noqa: F401  (registers tables)
from app.core.config import Settings, get_settings
from app.core.database import Base, make_engine
from app.modules.auth.router import router as auth_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.imaging.storage import LocalStorage
from app.modules.inference.engine import load_engine
from app.modules.inference.protocol import ImageModel
from app.modules.patients.router import router as patients_router
from app.modules.reviews.router import router as reviews_router
from app.modules.risk.router import router as risk_router
from app.modules.screenings.router import router as screenings_router

log = logging.getLogger("app")

# Each module contributes one router. Adding a module (e.g. clinical data) = write it + append here.
API_ROUTERS = [auth_router, patients_router, screenings_router, risk_router, reviews_router, dashboard_router]


def create_app(settings: Settings | None = None,
               engine_loader: Callable[[Settings], ImageModel | None] = load_engine) -> FastAPI:
    """engine_loader is injectable so tests (or a future remote-inference client) can supply the model."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Image.MAX_IMAGE_PIXELS = settings.max_image_pixels
        db_engine = make_engine(settings.database_url)
        Base.metadata.create_all(db_engine)  # TODO before production: switch to Alembic migrations
        app.state.settings = settings
        app.state.db_engine = db_engine
        app.state.session_factory = sessionmaker(db_engine, expire_on_commit=True)
        app.state.storage = LocalStorage(settings.storage_dir)
        app.state.engine = engine_loader(settings)
        yield
        db_engine.dispose()

    prod = settings.env == "production"
    app = FastAPI(title="Ophthalmic Screening API (fundus)", version="0.1.0", lifespan=lifespan,
                  docs_url=None if prod else "/docs", redoc_url=None if prod else "/redoc", openapi_url=None if prod else "/openapi.json")

    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
                           allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])

    @app.middleware("http")
    async def guard_and_headers(request: Request, call_next):
        # Cheap early rejection of oversized bodies (chunked uploads still need a proxy limit, see README).
        if request.method in ("POST", "PUT", "PATCH"):
            try:
                declared = int(request.headers.get("content-length", "0") or 0)
            except ValueError:
                declared = 0
            if declared > 2 * settings.max_upload_bytes + (1 << 20):
                return JSONResponse({"detail": "Request body too large"}, status_code=413)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")  # responses contain patient data
        return response

    for r in API_ROUTERS:
        app.include_router(r, prefix="/api/v1")

    @app.get("/health", tags=["system"])
    def health(request: Request):
        db_ok = True
        try:
            with request.app.state.db_engine.connect() as c:
                c.execute(text("SELECT 1"))
        except Exception:
            db_ok = False
        eng = request.app.state.engine
        ok = db_ok and eng is not None
        return JSONResponse({"status": "ok" if ok else "degraded", "database": db_ok, "model_loaded": eng is not None,
                             "model_tag": eng.info.tag if eng else None}, status_code=200 if db_ok else 503)

    return app

