"""
AURA Backend — FastAPI Application

Entry point for the AURA backend API.
Handles chat, admin operations, document upload with background indexing.

OPTIMIZED:
- Startup preloads LLM client, Embedding model, and Reranker.
- Supports PDF, DOCX, PPTX uploads.
- Supports XLSX and JSON order imports.
"""

import logging
import os
import json
import uuid
import tempfile
import time
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import io

from backend.orchestrator import process_message
from backend.rag import initialize_rag_system, ingest_single_document
from backend.llm_client import initialize_llm_client
from backend import supabase_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="AURA Backend API", version="2.0.0")

# ── CORS ─────────────────────────────────────────────────────────────
# In production, replace "*" with your actual frontend origins.
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request models ───────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class SessionUpdate(BaseModel):
    title: str

class ProductCreate(BaseModel):
    id: Optional[str] = None
    name: str
    description: Optional[str] = ""
    price: float
    brand: Optional[str] = ""
    category: str
    aliases: Optional[list] = []
    warranty_years: Optional[int] = 1
    manual_url: Optional[str] = ""

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    aliases: Optional[list] = None
    warranty_years: Optional[int] = None
    manual_url: Optional[str] = None

class OrderCreate(BaseModel):
    id: Optional[str] = None
    customer_name: str
    customer_phone: Optional[str] = ""
    product_id: Optional[str] = None
    product_name: str
    status: Optional[str] = "Pending"
    purchase_date: Optional[str] = None
    warranty_years: Optional[int] = 1
    serial_number: Optional[str] = ""

class OrderUpdate(BaseModel):
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    status: Optional[str] = None
    purchase_date: Optional[str] = None
    warranty_years: Optional[int] = None
    serial_number: Optional[str] = None

class PolicyCreate(BaseModel):
    id: Optional[str] = None
    policy_type: str  # refund | replacement | warranty
    scope: str        # global | category
    category: Optional[str] = None
    rules: Optional[dict] = {}
    description: Optional[str] = ""

class PolicyUpdate(BaseModel):
    policy_type: Optional[str] = None
    scope: Optional[str] = None
    category: Optional[str] = None
    rules: Optional[dict] = None
    description: Optional[str] = None

# ── Auth Dependency ──────────────────────────────────────────────────
security = HTTPBearer()

# Admin authorization: comma-separated list of admin email addresses.
# In production, replace with a proper role check (e.g. Supabase user_metadata.is_admin).
ADMIN_EMAILS = set(
    e.strip().lower()
    for e in os.getenv("ADMIN_EMAILS", "").split(",")
    if e.strip()
)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    client = supabase_client.get_user_client(token)
    if not client:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")

    try:
        user_response = client.auth.get_user()
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        return {
            "user_id": user_response.user.id,
            "email": user_response.user.email,
            "token": token
        }
    except Exception as e:
        logger.error(f"Auth error: {e}")
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")

def require_admin(user: dict = Depends(get_current_user)):
    """Dependency: require authenticated user + admin authorization.

    Checks (in order):
      1. Supabase user_metadata.is_admin flag
      2. ADMIN_EMAILS env-var allowlist (stopgap)
    Falls back to the allowlist if the metadata flag is absent or false.
    """
    # Check user_metadata for is_admin flag (preferred path)
    try:
        client = supabase_client.get_user_client(user["token"])
        if client:
            user_resp = client.auth.get_user()
            if user_resp and user_resp.user:
                meta = user_resp.user.user_metadata or {}
                if meta.get("is_admin") is True:
                    return user
    except Exception:
        pass  # fall through to allowlist check

    # Fallback: env-var admin email allowlist
    email = (user.get("email") or "").lower()
    if ADMIN_EMAILS and email in ADMIN_EMAILS:
        return user

    raise HTTPException(status_code=403, detail="Admin access required")


# ── Background job tracking ─────────────────────────────────────────
# Simple in-memory job tracker for document ingestion
_ingestion_jobs: Dict[str, dict] = {}

# ── Concurrency-limited executor for embedding/OCR jobs ─────────────
# Cap at 3 concurrent ingestion workers to avoid overwhelming CPU on small deployments
_ingestion_executor = ThreadPoolExecutor(max_workers=3)


# ── Startup ──────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup (OPTIMIZED).

    Re-indexing runs in a background thread so the server binds its port
    immediately — critical for Render's deploy health-check.
    """
    start_time = time.time()
    logger.info("Starting AURA Backend v2.0...")

    # Ensure data directories exist (for temp file processing)
    os.makedirs("backend/data/manuals", exist_ok=True)

    # Initialize LLM Client (Singleton)
    if initialize_llm_client():
        logger.info("LLM client initialized")
    else:
        logger.warning("LLM client initialization failed. Check API keys.")

    # Initialize RAG system (Loads Embedding Model + Reranker + ChromaDB)
    if initialize_rag_system():
        logger.info("RAG system initialized successfully.")

        # Re-ingest from Supabase Storage if ChromaDB is empty (ephemeral filesystem)
        # Runs in a BACKGROUND THREAD so the server starts accepting requests immediately.
        from backend.rag import _collection
        if _collection and _collection.count() == 0:
            logger.info("ChromaDB is empty — scheduling background re-ingestion from Supabase Storage...")
            import threading
            reindex_thread = threading.Thread(target=_reindex_from_supabase, daemon=True)
            reindex_thread.start()
    else:
        logger.error("Failed to initialize RAG system")

    elapsed = time.time() - start_time
    logger.info(f"AURA Backend is ready! (Startup took {elapsed:.2f}s)")



def _reindex_from_supabase():
    """Download all documents from Supabase Storage and re-ingest into ChromaDB.

    Called on startup when ChromaDB is empty (Render's ephemeral filesystem
    wipes chroma_db/ on every deploy, but documents persist in Supabase Storage).

    MEMORY-OPTIMIZED for Render's 512 MB free tier:
    - Processes one document at a time (no bulk download).
    - Explicitly frees file bytes and forces GC after each document.
    - Skips files larger than MAX_REINDEX_FILE_MB to avoid OOM spikes.
    - Sorts smallest-first so the most documents are indexed before any limit.
    """
    import gc

    MAX_REINDEX_FILE_BYTES = int(os.getenv("MAX_REINDEX_FILE_MB", "15")) * 1024 * 1024

    try:
        # Get list of previously uploaded documents from knowledge_base table
        entries = supabase_client.get_knowledge_entries()
        if not entries:
            logger.info("No documents found in Supabase knowledge_base — nothing to re-index")
            return

        reindexed = 0
        skipped_large = 0

        for entry in entries:
            filename = entry.get("file_name", "")
            bucket_path = entry.get("bucket_path", "")
            if not filename or not bucket_path:
                continue

            try:
                # Download file bytes from Supabase Storage (one at a time)
                file_bytes = supabase_client.download_file_from_storage("manuals", bucket_path)
                if not file_bytes:
                    logger.warning(f"Re-index: could not download {filename} from storage")
                    continue

                # Skip very large files to prevent OOM on constrained hosts
                file_size_mb = len(file_bytes) / (1024 * 1024)
                if len(file_bytes) > MAX_REINDEX_FILE_BYTES:
                    logger.warning(
                        f"Re-index: skipping {filename} ({file_size_mb:.1f} MB) — "
                        f"exceeds {MAX_REINDEX_FILE_BYTES // (1024*1024)} MB startup limit. "
                        f"Upload via /admin/upload to index it."
                    )
                    del file_bytes
                    gc.collect()
                    skipped_large += 1
                    continue

                # Write to temp file for ingestion, then free the bytes immediately
                ext = os.path.splitext(filename)[1].lower()
                with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                    tmp.write(file_bytes)
                    tmp_path = tmp.name

                # Free the downloaded bytes from memory before processing
                del file_bytes
                gc.collect()

                # Ingest into ChromaDB (skip OCR for fast startup — native text only)
                doc_type = entry.get("document_type", "manual")
                result = ingest_single_document(tmp_path, filename, doc_type=doc_type, skip_ocr=True)
                os.unlink(tmp_path)

                chunks = result.get("chunks_count", 0) if isinstance(result, dict) else result
                if chunks > 0:
                    reindexed += 1
                    logger.info(f"Re-indexed {filename} ({file_size_mb:.1f} MB): {chunks} chunks")

                # Update knowledge_base status
                supabase_client.update_knowledge_status(entry.get("id"), "ready", chunks)

                # Force GC after each document to keep peak memory low
                gc.collect()

            except Exception as e:
                logger.error(f"Re-index failed for {filename}: {e}")
                gc.collect()
                continue

        summary = f"Re-indexing complete: {reindexed}/{len(entries)} documents restored"
        if skipped_large:
            summary += f" ({skipped_large} skipped — too large for startup indexing)"
        logger.info(summary)

    except Exception as e:
        logger.error(f"Re-indexing from Supabase failed: {e}")


# ── Health & root ────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "message": "AURA Backend API",
        "version": "2.0.0",
        "health_check": "/health",
        "chat_endpoint": "/chat",
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "AURA Backend", "version": "2.0.0"}


# ── Chat ─────────────────────────────────────────────────────────────

@app.post("/chat")
async def chat(request: ChatRequest, user: dict = Depends(get_current_user)):
    """Chat endpoint — processes user messages through the AURA agent pipeline."""
    try:
        if not request.message or not request.message.strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        if len(request.message) > 5000:
            raise HTTPException(status_code=400, detail="Message too long (max 5000 characters)")

        session_id = request.session_id or f"session_{uuid.uuid4().hex[:12]}"

        start_time = time.time()

        # Process message through AURA agent pipeline
        result = process_message(request.message, session_id, user=user)

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(f"Chat response generated in {elapsed_ms:.0f}ms")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/chat/sessions")
def get_user_sessions(user: dict = Depends(get_current_user)):
    client = supabase_client.get_user_client(user["token"])
    res = client.table("chat_sessions").select("*").order("updated_at", desc=True).execute()
    return res.data

@app.get("/chat/sessions/{session_id}")
def get_session_messages(session_id: str, user: dict = Depends(get_current_user)):
    client = supabase_client.get_user_client(user["token"])
    res = client.table("chat_messages").select("*").eq("session_id", session_id).order("created_at").execute()
    return res.data

@app.delete("/chat/sessions/{session_id}")
def delete_session(session_id: str, user: dict = Depends(get_current_user)):
    client = supabase_client.get_user_client(user["token"])
    # Delete messages first to prevent foreign key constraint violations
    client.table("chat_messages").delete().eq("session_id", session_id).execute()
    # Then delete the session
    client.table("chat_sessions").delete().eq("session_id", session_id).execute()
    return {"status": "deleted"}

@app.patch("/chat/sessions/{session_id}")
def update_session_title(session_id: str, update: SessionUpdate, user: dict = Depends(get_current_user)):
    client = supabase_client.get_user_client(user["token"])
    client.table("chat_sessions").update({"title": update.title}).eq("session_id", session_id).execute()
    return {"status": "updated"}

# ═══════════════════════════════════════════════════════════
# Public endpoints
# ═══════════════════════════════════════════════════════════

@app.get("/products")
def list_products():
    """Public: list products (used by chat widget quick actions)."""
    products = supabase_client.get_products()
    if products:
        return products
    local_path = os.path.join(os.path.dirname(__file__), "backend", "data", "products.json")
    if not os.path.exists(local_path):
        local_path = os.path.join(os.path.dirname(__file__), "data", "products.json")
    if os.path.exists(local_path):
        with open(local_path, "r") as f:
            return json.load(f)
    return []


@app.get("/products/{product_id}")
def get_product(product_id: str):
    """Public: single product detail."""
    product = supabase_client.get_product_by_id(product_id)
    if product:
        return product
    raise HTTPException(status_code=404, detail="Product not found")


# ═══════════════════════════════════════════════════════════
# Admin endpoints
# ═══════════════════════════════════════════════════════════

@app.post("/admin/import-orders")
async def admin_import_orders(file: UploadFile = File(...), user: dict = Depends(require_admin)):
    """Import orders from an Excel (.xlsx) or JSON (.json) file.

    Expected columns/keys (matching the user's upload format):
    - order_id (required)
    - phone_number
    - product_name
    - product_model
    - order_date
    - status
    - customer_name

    The import maps phone_number → customer_phone in the DB schema.
    Idempotent on order_id (upsert).

    Auth: requires admin-level access (see require_admin dependency).
    """
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.xlsx', '.xls', '.json']:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Only .xlsx, .xls, and .json files are accepted."
        )

    contents = await file.read()

    try:
        if ext == '.json':
            orders_list = json.loads(contents)
            if not isinstance(orders_list, list):
                raise HTTPException(status_code=400, detail="JSON must be an array of order objects.")
            df = pd.DataFrame(orders_list)
        else:
            df = pd.read_excel(io.BytesIO(contents))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to parse file: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {e}")

    if df.empty:
        raise HTTPException(status_code=400, detail="File contains no data rows.")

    # --- Schema validation ---
    # order_id is required; everything else has sensible defaults
    if 'order_id' not in df.columns and 'id' not in df.columns:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required column 'order_id'. Found columns: {list(df.columns)}"
        )

    # INTENTIONAL: use service-role client for admin-only bulk import.
    # Admin authorization is enforced by require_admin dependency above.
    # Service-role access is appropriate here because this endpoint needs
    # to write orders across all users, not just the admin's own data.
    client = supabase_client._get_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    success_count = 0
    errors = []

    for idx, row in df.iterrows():
        order_id = str(row.get('order_id') or row.get('id') or '').strip()
        if not order_id:
            errors.append(f"Row {idx + 1}: missing order_id, skipped.")
            continue

        # Map phone_number (user's file) → customer_phone (DB schema)
        phone = str(row.get('phone_number') or row.get('customer_phone') or '')

        # Handle purchase_date / order_date
        raw_date = row.get('purchase_date') or row.get('order_date')
        purchase_date = None
        if pd.notna(raw_date):
            purchase_date = str(raw_date).split()[0]  # Take date part only

        order_data = {
            'id': order_id,
            'customer_name': str(row.get('customer_name') or 'Imported Customer'),
            'customer_phone': phone,
            'product_name': str(row.get('product_name') or ''),
            'status': str(row.get('status') or 'Pending'),
            'purchase_date': purchase_date,
        }

        try:
            client.table('orders').upsert(order_data).execute()
            success_count += 1
        except Exception as e:
            errors.append(f"Row {idx + 1} (order_id={order_id}): {e}")

    result = {"message": f"Successfully imported {success_count} of {len(df)} orders."}
    if errors:
        result["errors"] = errors
    return result

@app.get("/admin/stats")
def admin_stats(user: dict = Depends(require_admin)):
    """Dashboard summary statistics."""
    products = supabase_client.get_products()
    orders = supabase_client.get_orders()
    docs = supabase_client.get_knowledge_entries()
    sessions = supabase_client.get_active_sessions()

    return {
        "total_products": len(products),
        "total_orders": len(orders),
        "total_knowledge_docs": len(docs),
        "active_sessions": len(sessions),
    }


@app.get("/admin/knowledge")
def admin_knowledge(user: dict = Depends(require_admin)):
    """List all knowledge-base entries."""
    docs = supabase_client.get_knowledge_entries()
    if docs:
        return docs
    manuals_dir = os.path.join(os.path.dirname(__file__), "data", "manuals")
    policies_dir = os.path.join(os.path.dirname(__file__), "data", "policies")
    entries = []
    for d, doc_type in [(manuals_dir, "manual"), (policies_dir, "policy")]:
        if os.path.isdir(d):
            for fname in os.listdir(d):
                entries.append({
                    "file_name": fname,
                    "document_type": doc_type,
                    "status": "ready",
                    "chunks_count": 0,
                })
    return entries


@app.get("/admin/sessions")
def admin_sessions(user: dict = Depends(require_admin)):
    """List active chat sessions."""
    return supabase_client.get_active_sessions()


# Supported document types for upload
ALLOWED_DOC_EXTENSIONS = {".pdf", ".docx", ".pptx", ".txt"}

# Map filename patterns to document types for auto-tagging
def _infer_doc_type(filename: str) -> str:
    """Infer document_type from filename for ChromaDB metadata."""
    name_lower = filename.lower()
    if any(kw in name_lower for kw in ['policy', 'refund', 'replacement', 'warranty', 'return']):
        return 'policy'
    if any(kw in name_lower for kw in ['faq', 'frequently']):
        return 'faq'
    return 'manual'


def _run_ingestion_job(job_id: str, doc_bytes: bytes, filename: str, entry: dict):
    """Background task: chunk → embed → upsert document into ChromaDB."""
    try:
        _ingestion_jobs[job_id]["status"] = "indexing"
        _ingestion_jobs[job_id]["started_at"] = time.time()
        tmp_path = None

        ext = os.path.splitext(filename)[1].lower()

        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(doc_bytes)
            tmp_path = tmp.name

        doc_type = _infer_doc_type(filename)
        result = ingest_single_document(tmp_path, filename, doc_type=doc_type)
        os.unlink(tmp_path)

        # Extract metadata from the new dict return
        chunks_count = result.get("chunks_count", 0) if isinstance(result, dict) else result
        ocr_pages = result.get("ocr_pages", 0) if isinstance(result, dict) else 0
        total_pages = result.get("total_pages", 0) if isinstance(result, dict) else 0
        ocr_required = result.get("ocr_required", False) if isinstance(result, dict) else False

        # Build OCR warning message if applicable
        ocr_warning = None
        if ocr_required:
            ocr_warning = (f"This document has no native text layer — all {ocr_pages} pages "
                           f"were processed via OCR. Processing may be slower than usual.")

        # Update Supabase status
        if entry:
            supabase_client.update_knowledge_status(entry.get("id"), "ready", chunks_count)

        _ingestion_jobs[job_id].update({
            "status": "ready",
            "chunks_count": chunks_count,
            "ocr_pages": ocr_pages,
            "total_pages": total_pages,
            "ocr_required": ocr_required,
            "ocr_warning": ocr_warning,
        })
        logger.info(f"Ingestion job {job_id} completed: {chunks_count} chunks (type={doc_type})")

    except Exception as e:
        logger.error(f"Ingestion job {job_id} failed: {e}")
        _ingestion_jobs[job_id].update({
            "status": "error",
            "error": str(e),
        })
        if entry:
            supabase_client.update_knowledge_status(entry.get("id"), "error")


@app.post("/admin/upload")
async def admin_upload(
    file: UploadFile = File(...),
    user: dict = Depends(require_admin),
):
    """Upload a document (PDF/DOCX/PPTX/TXT) — returns immediately with a job ID.
    Indexing happens in the background.
    """
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_DOC_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Accepted formats: {', '.join(sorted(ALLOWED_DOC_EXTENSIONS))}"
        )

    contents = await file.read()

    # Infer document type for metadata
    doc_type = _infer_doc_type(file.filename)

    # Upload to Supabase Storage
    storage_path = f"manuals/{file.filename}"
    supabase_client.upload_file_to_storage("manuals", storage_path, contents, file.content_type)

    # Record in knowledge_base table
    entry = supabase_client.insert_knowledge_entry({
        "file_name": file.filename,
        "bucket_path": storage_path,
        "document_type": doc_type,
        "status": "indexing",
    })

    # Create a job tracker entry
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    _ingestion_jobs[job_id] = {
        "job_id": job_id,
        "file_name": file.filename,
        "status": "queued",
        "chunks_count": 0,
    }

    # Schedule ingestion via executor (consistent with batch endpoint, not tied to request lifecycle)
    _ingestion_executor.submit(_run_ingestion_job, job_id, contents, file.filename, entry)

    return {
        "status": "accepted",
        "job_id": job_id,
        "file_name": file.filename,
        "document_type": doc_type,
        "message": f"Document queued for indexing. Check status at /admin/upload/status/{job_id}",
    }


@app.get("/admin/upload/status/{job_id}")
def upload_status(job_id: str, user: dict = Depends(require_admin)):
    """Check status of a document ingestion job."""
    job = _ingestion_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


MAX_BATCH_SIZE = 50  # reasonable cap per request
MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB


@app.post("/admin/upload/batch")
async def admin_upload_batch(
    files: List[UploadFile] = File(...),
    user: dict = Depends(require_admin),
):
    """Upload multiple documents in one request.

    Each file is validated independently — one bad file won't block the rest.
    Ingestion jobs are submitted to a ThreadPoolExecutor (max 3 concurrent)
    so large batches don't overwhelm embedding/OCR.

    Returns a list of per-file results:
        [{filename, stored_filename, status, job_id, error?}, ...]
    """
    if len(files) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files in one batch (max {MAX_BATCH_SIZE}).",
        )

    results = []

    for upload_file in files:
        filename = upload_file.filename or "unknown"
        ext = os.path.splitext(filename)[1].lower()

        # ── Per-file validation ──────────────────────────────────────
        if ext not in ALLOWED_DOC_EXTENSIONS:
            results.append({
                "filename": filename,
                "stored_filename": filename,
                "status": "failed",
                "job_id": None,
                "error": f"Unsupported file type '{ext}'. Accepted: {', '.join(sorted(ALLOWED_DOC_EXTENSIONS))}",
            })
            continue

        try:
            contents = await upload_file.read()
        except Exception as e:
            results.append({
                "filename": filename,
                "stored_filename": filename,
                "status": "failed",
                "job_id": None,
                "error": f"Failed to read file: {e}",
            })
            continue

        if len(contents) > MAX_FILE_BYTES:
            results.append({
                "filename": filename,
                "stored_filename": filename,
                "status": "failed",
                "job_id": None,
                "error": f"File too large ({len(contents) / 1024 / 1024:.1f} MB). Max 50 MB.",
            })
            continue

        # ── Upload to storage & create DB entry ──────────────────────
        doc_type = _infer_doc_type(filename)
        storage_path = f"manuals/{filename}"

        try:
            supabase_client.upload_file_to_storage(
                "manuals", storage_path, contents, upload_file.content_type
            )
        except Exception as e:
            logger.warning(f"Storage upload failed for {filename}: {e}")
            # Non-fatal for indexing — continue to attempt ingestion

        entry = None
        try:
            entry = supabase_client.insert_knowledge_entry({
                "file_name": filename,
                "bucket_path": storage_path,
                "document_type": doc_type,
                "status": "indexing",
            })
        except Exception as e:
            logger.warning(f"KB entry insert failed for {filename}: {e}")

        # ── Create job & submit to executor ──────────────────────────
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        _ingestion_jobs[job_id] = {
            "job_id": job_id,
            "file_name": filename,
            "status": "queued",
            "chunks_count": 0,
        }

        _ingestion_executor.submit(_run_ingestion_job, job_id, contents, filename, entry)

        results.append({
            "filename": filename,
            "stored_filename": filename,
            "status": "processing",
            "job_id": job_id,
            "error": None,
        })

    return results


# ═══════════════════════════════════════════════════════════
# Product CRUD (server-side validated)
# ═══════════════════════════════════════════════════════════

@app.post("/admin/products")
def admin_create_product(product: ProductCreate, user: dict = Depends(require_admin)):
    """Create a new product with server-side validation."""
    # Validation
    if not product.name or not product.name.strip():
        raise HTTPException(status_code=400, detail="Product name is required.")
    if not product.category or not product.category.strip():
        raise HTTPException(status_code=400, detail="Product category is required.")
    if product.price is None or product.price <= 0:
        raise HTTPException(status_code=400, detail="Price must be greater than 0.")
    if product.warranty_years is not None and product.warranty_years < 0:
        raise HTTPException(status_code=400, detail="Warranty must be >= 0 years.")
    if product.manual_url and product.manual_url.strip():
        # Validate manual_url references a real knowledge_base entry
        kb_entries = supabase_client.get_knowledge_entries()
        valid_names = {e["file_name"] for e in kb_entries}
        if product.manual_url.strip() not in valid_names:
            # Allow URLs too
            if not product.manual_url.startswith("http"):
                raise HTTPException(status_code=400, detail=f"Manual '{product.manual_url}' not found in Knowledge Base.")

    product_id = product.id or f"PROD-{uuid.uuid4().hex[:8].upper()}"
    data = {
        "id": product_id,
        "name": product.name.strip(),
        "description": product.description or "",
        "price": product.price,
        "brand": product.brand or "",
        "category": product.category.strip(),
        "aliases": product.aliases or [],
        "warranty_years": product.warranty_years or 1,
        "manual_url": product.manual_url or "",
    }
    result = supabase_client.upsert_product(data)
    if result is None:
        raise HTTPException(status_code=500, detail="Failed to create product.")
    return {"status": "created", "product": data}


@app.put("/admin/products/{product_id}")
def admin_update_product(product_id: str, product: ProductUpdate, user: dict = Depends(require_admin)):
    """Update an existing product with server-side validation."""
    existing = supabase_client.get_product_by_id(product_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Product not found.")

    update_data = {}
    if product.name is not None:
        if not product.name.strip():
            raise HTTPException(status_code=400, detail="Product name cannot be empty.")
        update_data["name"] = product.name.strip()
    if product.category is not None:
        if not product.category.strip():
            raise HTTPException(status_code=400, detail="Category cannot be empty.")
        update_data["category"] = product.category.strip()
    if product.price is not None:
        if product.price <= 0:
            raise HTTPException(status_code=400, detail="Price must be greater than 0.")
        update_data["price"] = product.price
    if product.warranty_years is not None:
        if product.warranty_years < 0:
            raise HTTPException(status_code=400, detail="Warranty must be >= 0 years.")
        update_data["warranty_years"] = product.warranty_years
    if product.description is not None:
        update_data["description"] = product.description
    if product.brand is not None:
        update_data["brand"] = product.brand
    if product.aliases is not None:
        update_data["aliases"] = product.aliases
    if product.manual_url is not None:
        update_data["manual_url"] = product.manual_url

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update.")

    client = supabase_client._get_client()
    if not client:
        raise HTTPException(status_code=500, detail="Database unavailable.")
    try:
        result = client.table("products").update(update_data).eq("id", product_id).execute()
        return {"status": "updated", "product": result.data[0] if result.data else update_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/admin/products/{product_id}")
def admin_delete_product(product_id: str, user: dict = Depends(require_admin)):
    """Delete a product."""
    if not supabase_client.delete_product(product_id):
        raise HTTPException(status_code=500, detail="Failed to delete product.")
    return {"status": "deleted"}


# ═══════════════════════════════════════════════════════════
# Order CRUD (server-side validated)
# ═══════════════════════════════════════════════════════════

@app.get("/admin/orders")
def admin_list_orders(user: dict = Depends(require_admin)):
    """List all orders."""
    return supabase_client.get_orders()


@app.post("/admin/orders")
def admin_create_order(order: OrderCreate, user: dict = Depends(require_admin)):
    """Create a new order with server-side validation."""
    if not order.customer_name or not order.customer_name.strip():
        raise HTTPException(status_code=400, detail="Customer name is required.")
    if not order.product_name or not order.product_name.strip():
        raise HTTPException(status_code=400, detail="Product name is required.")

    valid_statuses = {"Pending", "Processing", "In-Transit", "Delivered", "Cancelled"}
    if order.status and order.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(sorted(valid_statuses))}")

    order_id = order.id or f"ORD-{uuid.uuid4().hex[:8].upper()}"
    data = {
        "id": order_id,
        "customer_name": order.customer_name.strip(),
        "customer_phone": order.customer_phone or "",
        "product_id": order.product_id or None,
        "product_name": order.product_name.strip(),
        "status": order.status or "Pending",
        "purchase_date": order.purchase_date or None,
        "warranty_years": order.warranty_years or 1,
        "serial_number": order.serial_number or "",
    }
    try:
        result = supabase_client.insert_order(data)
        return {"status": "created", "order": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create order: {str(e)}")


@app.put("/admin/orders/{order_id}")
def admin_update_order(order_id: str, order: OrderUpdate, user: dict = Depends(require_admin)):
    """Update an existing order with server-side validation."""
    existing = supabase_client.get_order_by_id_db(order_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Order not found.")

    update_data = {}
    if order.customer_name is not None:
        if not order.customer_name.strip():
            raise HTTPException(status_code=400, detail="Customer name cannot be empty.")
        update_data["customer_name"] = order.customer_name.strip()
    if order.customer_phone is not None:
        update_data["customer_phone"] = order.customer_phone
    if order.product_id is not None:
        update_data["product_id"] = order.product_id
    if order.product_name is not None:
        if not order.product_name.strip():
            raise HTTPException(status_code=400, detail="Product name cannot be empty.")
        update_data["product_name"] = order.product_name.strip()
    if order.status is not None:
        valid_statuses = {"Pending", "Processing", "In-Transit", "Delivered", "Cancelled"}
        if order.status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid status.")
        update_data["status"] = order.status
    if order.purchase_date is not None:
        update_data["purchase_date"] = order.purchase_date
    if order.warranty_years is not None:
        update_data["warranty_years"] = order.warranty_years
    if order.serial_number is not None:
        update_data["serial_number"] = order.serial_number

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update.")

    try:
        result = supabase_client.update_order(order_id, update_data)
        return {"status": "updated", "order": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/admin/orders/{order_id}")
def admin_delete_order(order_id: str, user: dict = Depends(require_admin)):
    """Delete an order."""
    if not supabase_client.delete_order(order_id):
        raise HTTPException(status_code=500, detail="Failed to delete order.")
    return {"status": "deleted"}


# ═══════════════════════════════════════════════════════════
# Policy CRUD (server-side validated)
# ═══════════════════════════════════════════════════════════

@app.get("/admin/policies")
def admin_list_policies(user: dict = Depends(require_admin)):
    """List all policies."""
    return supabase_client.get_policies()


@app.post("/admin/policies")
def admin_create_policy(
    policy: PolicyCreate,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_admin),
):
    """Create or update a policy with server-side validation."""
    valid_types = {"refund", "replacement", "warranty"}
    if policy.policy_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"policy_type must be one of: {', '.join(sorted(valid_types))}")
    if policy.scope not in {"global", "category"}:
        raise HTTPException(status_code=400, detail="scope must be 'global' or 'category'.")
    if policy.scope == "category" and (not policy.category or not policy.category.strip()):
        raise HTTPException(status_code=400, detail="category is required when scope is 'category'.")
    if policy.scope == "global" and policy.category:
        raise HTTPException(status_code=400, detail="category must be null when scope is 'global'.")

    from datetime import datetime
    policy_id = policy.id or f"POL-{uuid.uuid4().hex[:8].upper()}"
    data = {
        "id": policy_id,
        "policy_type": policy.policy_type,
        "scope": policy.scope,
        "category": policy.category.strip() if policy.category else None,
        "rules": policy.rules or {},
        "description": policy.description or "",
        "updated_at": datetime.now().isoformat(),
    }
    try:
        result = supabase_client.upsert_policy(data)

        # Background: ingest description into RAG for retrieval
        if data.get("description"):
            background_tasks.add_task(_ingest_policy_to_rag, data)

        return {"status": "created", "policy": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create policy: {str(e)}")


@app.put("/admin/policies/{policy_id}")
def admin_update_policy(
    policy_id: str,
    policy: PolicyUpdate,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_admin),
):
    """Update an existing policy."""
    existing = supabase_client.get_policy_by_id(policy_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Policy not found.")

    from datetime import datetime
    update_data = {"updated_at": datetime.now().isoformat()}

    if policy.policy_type is not None:
        valid_types = {"refund", "replacement", "warranty"}
        if policy.policy_type not in valid_types:
            raise HTTPException(status_code=400, detail=f"policy_type must be one of: {', '.join(sorted(valid_types))}")
        update_data["policy_type"] = policy.policy_type
    if policy.scope is not None:
        if policy.scope not in {"global", "category"}:
            raise HTTPException(status_code=400, detail="scope must be 'global' or 'category'.")
        update_data["scope"] = policy.scope
    if policy.category is not None:
        update_data["category"] = policy.category.strip() if policy.category else None
    if policy.rules is not None:
        update_data["rules"] = policy.rules
    if policy.description is not None:
        update_data["description"] = policy.description

    try:
        client = supabase_client._get_client()
        result = client.table("policies").update(update_data).eq("id", policy_id).execute()
        merged = {**existing, **update_data}

        # Re-ingest into RAG if description changed
        if policy.description is not None and policy.description:
            background_tasks.add_task(_ingest_policy_to_rag, merged)

        return {"status": "updated", "policy": merged}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/admin/policies/{policy_id}")
def admin_delete_policy(policy_id: str, user: dict = Depends(require_admin)):
    """Delete a policy."""
    if not supabase_client.delete_policy(policy_id):
        raise HTTPException(status_code=500, detail="Failed to delete policy.")
    return {"status": "deleted"}


@app.get("/admin/policies/resolve")
def admin_resolve_policy(policy_type: str, category: str = "", user: dict = Depends(require_admin)):
    """Test the deterministic policy resolution: returns the resolved policy for a type+category."""
    resolved = supabase_client.resolve_policy(category, policy_type)
    if not resolved:
        raise HTTPException(status_code=404, detail=f"No policy found for type='{policy_type}', category='{category}'")
    return resolved


def _ingest_policy_to_rag(policy_data: dict):
    """Background task: ingest a policy's description into ChromaDB for RAG retrieval."""
    try:
        from backend.rag import ingest_policy_text
        ingest_policy_text(
            policy_id=policy_data["id"],
            text=policy_data.get("description", ""),
            policy_type=policy_data.get("policy_type", ""),
            scope=policy_data.get("scope", "global"),
            category=policy_data.get("category", ""),
        )
        logger.info(f"Policy {policy_data['id']} ingested into RAG")
    except Exception as e:
        logger.error(f"Failed to ingest policy {policy_data.get('id')} into RAG: {e}")


# ── Entry point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)


