"""
FastAPI application for MOTEL backend services.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.src.api.filter import router as filter_router
from backend.src.api.technologies import router as technologies_router
from backend.src.config import get_backend_settings


settings = get_backend_settings()

app = FastAPI(
    title="MOTEL Backend API",
    description="API for technology conversion and export from MOTEL ontology",
    version="0.1.0",
)

# Configure CORS to allow requests from frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(filter_router)
app.include_router(technologies_router)


@app.get("/")
async def root() -> dict:
    """Root endpoint."""
    return {
        "message": "MOTEL Backend API",
        "docs": "/docs",
        "health": {
            "filter": "/api/filter/health",
            "technologies": "/api/technologies/health",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.src.server:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
