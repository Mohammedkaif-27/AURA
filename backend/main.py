import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from backend.orchestrator import process_message
from backend.rag import initialize_rag_system, load_manuals_into_rag

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="AURA Backend API", version="1.0.0")

# Add CORS middleware for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request model for validation
class ChatRequest(BaseModel):
    message: str
    session_id: str = None  # Optional session ID for conversation memory


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("Starting AURA Backend...")
    
    # Initialize RAG system
    if initialize_rag_system():
        logger.info("RAG system initialized")
        
        # Try to load manuals
        if load_manuals_into_rag():
            logger.info("Manuals loaded successfully")
        else:
            logger.warning("WARNING: No manuals loaded - agent will work with limited context")
    else:
        logger.error("ERROR: Failed to initialize RAG system")
    
    logger.info("AURA Backend is ready!")


@app.get("/health")
def health():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "AURA Backend",
        "version": "1.0.0"
    }


@app.post("/chat")
async def chat(request: ChatRequest):
    """Chat endpoint with error handling and validation"""
    try:
        import uuid
        
        # Validate message
        if not request.message or not request.message.strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty")
        
        if len(request.message) > 5000:
            raise HTTPException(status_code=400, detail="Message too long (max 5000 characters)")
        
        logger.info(f"Received chat request: {request.message[:50]}...")
        
        # Generate session_id if not provided
        session_id = request.session_id or f"session_{uuid.uuid4().hex[:12]}"
        logger.info(f"Using session_id: {session_id}")
        
        # Process message through AURA agent pipeline with session
        result = process_message(request.message, session_id)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ERROR: Error in chat endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
