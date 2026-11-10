from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from api.presentation.errors import register_error_handlers
from api.presentation.routers import admin, auth, downloads, registry, uploads
from api.presentation.services import ApiServices


API_PREFIX = "/v1"


def create_app(services: ApiServices) -> FastAPI:
    """Assemble the FastAPI application around the injected use cases.

    Every router is mounted under ``/v1``, and expired sessions are
    cleaned before the application starts serving.

    Args:
        services: Use cases built by the composition root.

    Returns:
        The application.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Free what idle sessions left behind before serving.
        """Free what idle sessions left behind before serving.

        Args:
            app: The application that is starting.

        Yields:
            Control while the application runs.
        """
        await run_in_threadpool(services.cleanup.execute)
        yield

    app = FastAPI(title="easyk8s api", version="1.0.0", lifespan=lifespan)
    app.state.services = services

    register_error_handlers(app)

    for module in (auth, uploads, downloads, registry, admin):
        app.include_router(module.router, prefix=API_PREFIX)

    return app
