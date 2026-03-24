from __future__ import annotations

from fastapi import FastAPI

from specflow import __version__


def create_app() -> FastAPI:
    """Create the platform API application."""
    application = FastAPI(title="SpecFlow-Agent API", version=__version__)

    @application.get("/healthz", tags=["system"])
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return application


app = create_app()
