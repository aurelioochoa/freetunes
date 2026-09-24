import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .logging_setup import POLLING_PATH_PREFIXES, get_logger, setup_logging
from .routers import apps, backup, devices, diagnostics, files, firmware, library, screen, sync, toolbox
from .services.screen import begin_shutdown

setup_logging()
log = get_logger("api")


def _is_polling_success(path: str, status: int) -> bool:
    return 200 <= status < 300 and path.split("?", 1)[0].startswith(POLLING_PATH_PREFIXES)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    log.info("backend up mock=%s http://127.0.0.1:8000 ui=http://127.0.0.1:5173",
             os.environ.get("FREETUNES_MOCK", "0"))
    yield
    # Release the MJPEG streams so shutdown (and every --reload) can
    # finish: uvicorn waits on in-flight responses, and a live <img>
    # stream is in flight until someone tells it to stop.
    begin_shutdown()
    log.info("backend shutdown")


def create_app() -> FastAPI:
    app = FastAPI(title="freetunes", version="0.1.0",
                  lifespan=_lifespan,
                  description="FOSS web iTunes clone daemon (Finder + Music UI)")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(devices.router)
    app.include_router(apps.router)
    app.include_router(library.router)
    app.include_router(sync.router)
    app.include_router(backup.router)
    app.include_router(files.router)
    app.include_router(diagnostics.router)
    app.include_router(toolbox.router)
    app.include_router(firmware.router)
    app.include_router(screen.router)

    @app.middleware("http")
    async def _request_log(request: Request, call_next):
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            log.exception("%s %s failed in %.0fms",
                          request.method, request.url.path, elapsed_ms)
            raise
        elapsed_ms = (time.perf_counter() - started) * 1000
        msg = "%s %s -> %d in %.0fms"
        args = (request.method, request.url.path, response.status_code, elapsed_ms)
        if response.status_code >= 500:
            log.error(msg, *args)
        elif response.status_code >= 400:
            log.warning(msg, *args)
        elif _is_polling_success(request.url.path, response.status_code):
            log.debug(msg, *args)
        else:
            log.info(msg, *args)
        return response

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "freetunes", "mock": True}

    return app


app = create_app()
