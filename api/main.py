"""ASGI entry point: uvicorn api.main:create --factory"""
from fastapi import FastAPI

from api.infraestructure.composition import build_app
from api.infraestructure.settings import Settings


def create() -> FastAPI:
    """Build the application from the environment.

    Used as ASGI factory: ``uvicorn api.main:create --factory``.

    Returns:
        The application.
    """
    return build_app(Settings.from_env())
