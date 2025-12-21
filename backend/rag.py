import os
import glob
import logging
import chromadb
from chromadb.config import Settings
from pypdf import PdfReader
from dotenv import load_dotenv
from vertexai.language_models import TextEmbeddingModel

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize globals - Using Vertex AI embeddings (no PyTorch required)
embedder = None
chroma_client = None
collection = None
_initialized = False


def _load_embedding_model():
    """Load Vertex AI Text Embedding model (no PyTorch DLL issues)"""
    try:
        model = TextEmbeddingModel.from_pretrained("text-embedding-004")
        logger.info("Loaded Vertex AI embedding model")
        return model
    except Exception as e:
        logger.error(f"ERROR: Failed to load Vertex AI embedding model: {e}")
        raise


def initialize_rag_system():
    """Initialize the RAG system with error handling"""
    global embedder, chroma_client, collection, _initialized
    
    if _initialized:
        logger.info("RAG system already initialized")
        return True
    
    try:
        logger.info("Initializing RAG system...")
        
        # Load embedding model (Vertex AI)
        embedder = _load_embedding_model()
        logger.info("Embedding model loaded")
        
        # Initialize ChromaDB
        chroma_client = chromadb.PersistentClient(
            path="backend/chroma_db",
            settings=Settings(allow_reset=True)
        )
        
        collection = chroma_client.get_or_create_collection(
            name="aura_manuals",
            metadata={"hnsw:space": "cosine"}
        )
        logger.info("ChromaDB initialized")
        
        _initialized = True
        return True
        
    except Exception as e:
        logger.error(f"ERROR: Failed to initialize RAG system: {e}")
        return False


def chunk_text(text, chunk_size=450, overlap=50):
    """Split text into overlapping chunks"""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += (chunk_size - overlap)
    return chunks


def load_manuals_into_rag():
    """Load PDF manuals into RAG database with error handling"""
    try:
        if not _initialized:
            logger.warning("RAG system not initialized, initializing now...")
            if not initialize_rag_system():
                return False
        
        pdf_files = glob.glob("backend/data/manuals/*.pdf")
        
        if not pdf_files:
            logger.warning("WARNING: No PDF manuals found in backend/data/manuals/")
            return False

        docs = []
        ids = []

        for pdf in pdf_files:
            try:
                reader = PdfReader(pdf)
                full_text = ""
                for page in reader.pages:
                    full_text += page.extract_text() + "\n"

                parts = chunk_text(full_text)
                for i, ch in enumerate(parts):
                    docs.append(ch)
                    ids.append(f"{os.path.basename(pdf)}_{i}")
                    
                logger.info(f"Loaded {os.path.basename(pdf)}")
                
            except Exception as e:
                logger.error(f"ERROR: Failed to load {pdf}: {e}")
                continue

        if not docs:
            logger.warning("WARNING: No documents extracted from PDFs")
            return False

        # Vertex AI embeddings API - process in batches of 5 (API limit)
        vectors = []
        batch_size = 5
        for i in range(0, len(docs), batch_size):
            batch = docs[i:i + batch_size]
            embeddings = embedder.get_embeddings(batch)
            vectors.extend([emb.values for emb in embeddings])

        collection.upsert(
            documents=docs,
            embeddings=vectors,
            ids=ids
        )

        logger.info(f"Successfully loaded {len(pdf_files)} manuals with {len(docs)} chunks")
        return True
        
    except Exception as e:
        logger.error(f"ERROR: Error loading manuals: {e}")
        return False


def search_knowledge(query, k=5):
    """Search the knowledge base with error handling"""
    try:
        if not _initialized:
            logger.warning("RAG system not initialized, cannot search")
            return []
        
        # Get embedding for query using Vertex AI
        embedding = embedder.get_embeddings([query])[0]
        vec = embedding.values

        results = collection.query(
            query_embeddings=[vec],
            n_results=k
        )

        if "documents" in results and results["documents"]:
            return results["documents"][0]

        return []
        
    except Exception as e:
        logger.error(f"ERROR: Error searching knowledge base: {e}")
        return []
