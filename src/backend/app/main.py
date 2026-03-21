"""Unravel backend — FastAPI application entry point."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.session_routes import router as session_router

app = FastAPI(
    title="Unravel",
    description="Kubernetes support bundle AI analyzer",
    version="0.1.0",
)

cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(session_router)

from app.rag import rag_store
from app.sessions.store import session_store


def _cleanup_chroma(session):
    if session.chroma_collection_name:
        rag_store.delete_collection(session.chroma_collection_name)


session_store.register_cleanup_hook(_cleanup_chroma)


@app.get("/api/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}
