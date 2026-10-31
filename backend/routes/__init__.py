"""FastAPI route modules. app.py only creates the app and includes these."""

from backend.routes import core, product, tier  # noqa: F401

__all__ = ["core", "product", "tier"]
