from fastapi import FastAPI
from . import utils

from .routers import (
    note,
    provider,
    model,
    config,
    media,
    ocr,
    note_group,
    general,
)


def create_app(lifespan) -> FastAPI:
    app = FastAPI(title="BiliNote", lifespan=lifespan)
    app.include_router(note.router, prefix="/api")
    app.include_router(provider.router, prefix="/api")
    app.include_router(model.router, prefix="/api")
    app.include_router(config.router, prefix="/api")
    app.include_router(media.router, prefix="/api")
    app.include_router(ocr.router, prefix="/api")
    app.include_router(note_group.router, prefix="/api")
    app.include_router(general.router, prefix="/api")

    return app
