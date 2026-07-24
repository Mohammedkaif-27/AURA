"""
AURA Backend — Centralized Configuration

Purpose:
    Single source of truth for every tunable setting in the backend.
    All model names, paths, feature flags, and credentials are loaded
    here from environment variables (via .env).  Every other module
    imports from this file — no hardcoded strings elsewhere.

Responsibilities:
    - Load .env at startup
    - Expose constants for: LLM models, embedding models, ChromaDB,
      chunking, retrieval, feature flags, and admin security
    - Auto-detect GPU (CUDA) vs CPU for model inference

Used By:
    main.py, rag.py, llm_client.py, orchestrator.py, agents.py

Depends On:
    python-dotenv, torch (optional)

Related Files:
    .env            — actual values (never committed)
    .env.example    — template with documentation
"""

import os
import logging

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# ==========================================================
# LLM & EMBEDDING MODELS
# ==========================================================
# EMBEDDING_MODEL  — used by rag.py to convert text into vectors.
# RERANKER_MODEL   — used by rag.py to re-score retrieved chunks.
# Both run locally via HuggingFace sentence-transformers.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")


# ==========================================================
# DEVICE SELECTION
# ==========================================================
# Why?  Embedding and reranking models can run on GPU (CUDA) for
# faster inference.  On most deployments there
# is no GPU, so we fall back to CPU automatically.
try:
    import torch
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
except ImportError:
    DEVICE = "cpu"


# ==========================================================
# CHROMADB (Vector Database)
# ==========================================================
# CHROMA_DB_PATH       — directory where ChromaDB persists vectors.
# CHROMA_COLLECTION    — collection name inside ChromaDB.
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "backend/chroma_db")
CHROMA_COLLECTION = "aura_manuals"


# ==========================================================
# VERSIONING
# ==========================================================
AURA_VERSION = "2.1"


# ==========================================================
# CHUNKING PARAMETERS
# ==========================================================
# Why?  Large documents are split into small "chunks" before being
# stored as vectors.  CHUNK_SIZE_TOKENS controls how many tokens per
# chunk.  CHUNK_OVERLAP_RATIO prevents splitting mid-sentence by
# overlapping adjacent chunks.
CHUNK_SIZE_TOKENS = int(os.getenv("CHUNK_SIZE_TOKENS", "350"))
CHUNK_OVERLAP_RATIO = float(os.getenv("CHUNK_OVERLAP_RATIO", "0.15"))


# ==========================================================
# RETRIEVAL
# ==========================================================
# How many candidate chunks to fetch from ChromaDB before reranking.
# More candidates = higher recall but slower reranking.
RETRIEVAL_CANDIDATES = int(os.getenv("RETRIEVAL_CANDIDATES", "20"))


# ==========================================================
# FEATURE FLAGS
# ==========================================================
# ENABLE_QUERY_EXPANSION  — if True, the LLM rewrites the user's
#     question into a richer query before searching.
# ENABLE_HYBRID_SEARCH    — if True, both vector search AND BM25
#     keyword search are used (combined via Reciprocal Rank Fusion).
ENABLE_QUERY_EXPANSION = os.getenv("ENABLE_QUERY_EXPANSION", "true").lower() == "true"
ENABLE_HYBRID_SEARCH = os.getenv("ENABLE_HYBRID_SEARCH", "true").lower() == "true"


# ==========================================================
# ADMIN / SECURITY
# ==========================================================
# ADMIN_API_KEY              — key required to hit /admin/rebuild-collection.
# ENABLE_REBUILD_ENDPOINT    — safety switch; must be True to allow rebuilds.
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
ENABLE_REBUILD_ENDPOINT = os.getenv("ENABLE_REBUILD_ENDPOINT", "false").lower() == "true"
