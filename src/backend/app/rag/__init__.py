"""RAG (Retrieval Augmented Generation) package for semantic search over bundle content."""

from app.rag.embedder import RAGStore

# Global singleton instance — imported by routes.py and main.py
rag_store = RAGStore()
