"""UnClaude Web Dashboard package."""


def create_app():
    """Create the FastAPI application (lazy import)."""
    from unclaude.web.server import create_app as _create_app
    return _create_app()


__all__ = ["create_app"]
