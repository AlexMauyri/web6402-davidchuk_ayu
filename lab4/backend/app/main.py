from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.api.exception_handlers import register_exception_handlers
from app.api.router import router
from app.config import Settings, settings
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await engine.dispose()


def create_app(config: Settings = settings) -> FastAPI:
    secret = config.session_secret_key
    if secret is None or len(secret.get_secret_value().encode()) < 32:
        raise ValueError("SESSION_SECRET_KEY должен содержать не менее 32 байт")
    application = FastAPI(lifespan=lifespan)
    application.state.session_ttl = config.session_ttl
    application.add_middleware(
        SessionMiddleware,
        secret_key=secret.get_secret_value(),
        session_cookie="forum_session",
        max_age=config.session_ttl,
        path="/api",
        same_site="lax",
        https_only=config.cookie_secure,
    )
    register_exception_handlers(application)
    application.include_router(router)
    application.add_api_route("/health", health, methods=["GET"], status_code=200)
    return application


async def health():
    return {"status": "ok"}


app = create_app()
