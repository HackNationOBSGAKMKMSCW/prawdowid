"""RAG (osoba A): ingest źródeł do Qdrant i `retrieve()` dla części werdyktu.

from prawdowid_analysis.rag import get_retriever, ingest_sources
"""

from .ingest import ingest_sources
from .retriever import get_retriever, retrieve

__all__ = ["get_retriever", "ingest_sources", "retrieve"]
