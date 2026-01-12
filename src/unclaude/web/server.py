"""FastAPI server for UnClaude Web Dashboard."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from unclaude.web.routes import chat, memory, jobs, settings, ralph, plugins, skills, mcp


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="UnClaude Dashboard",
        description="Local-first AI coding assistant dashboard",
        version="0.2.0",
    )

    # CORS for local development (allows Next.js frontend to connect)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes (must be registered before static files)
    app.include_router(chat.router, prefix="/api", tags=["chat"])
    app.include_router(memory.router, prefix="/api", tags=["memory"])
    app.include_router(jobs.router, prefix="/api", tags=["jobs"])
    app.include_router(settings.router, prefix="/api", tags=["settings"])
    app.include_router(ralph.router, prefix="/api", tags=["ralph"])
    app.include_router(plugins.router, prefix="/api", tags=["plugins"])
    app.include_router(skills.router, prefix="/api", tags=["skills"])
    app.include_router(mcp.router, prefix="/api", tags=["mcp"])

    # Serve static files from built Next.js export
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists() and static_dir.is_dir():
        # Serve static assets
        app.mount("/_next", StaticFiles(directory=static_dir / "_next"), name="next_static")
        
        # Serve other static files (favicon, etc.)
        if (static_dir / "favicon.ico").exists():
            @app.get("/favicon.ico")
            async def favicon():
                return FileResponse(static_dir / "favicon.ico")
        
        # Catch-all for HTML pages - serve index.html for SPA routing
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            # Try to serve the exact file first
            file_path = static_dir / full_path
            if file_path.exists() and file_path.is_file():
                return FileResponse(file_path)
            
            # Try with .html extension
            html_path = static_dir / f"{full_path}.html"
            if html_path.exists():
                return FileResponse(html_path)
            
            # Try as directory with index.html
            index_path = static_dir / full_path / "index.html"
            if index_path.exists():
                return FileResponse(index_path)
            
            # Fall back to root index.html (SPA routing)
            root_index = static_dir / "index.html"
            if root_index.exists():
                return FileResponse(root_index)
            
            # If no static files, return 404
            return {"error": "Not found", "path": full_path}

    return app


app = create_app()
