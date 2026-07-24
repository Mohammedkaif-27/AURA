# AURA Backend Architecture

> [!NOTE]
> This document explains the **high-level structure** of the AURA backend. For a step-by-step trace of how a single user message is handled, see [BACKEND_FLOW.md](./BACKEND_FLOW.md). For beginner-friendly explanations of FastAPI concepts, see [BACKEND_FOR_STUDENTS.md](./BACKEND_FOR_STUDENTS.md).

## Overview

The AURA Backend is a stateful conversational AI system built with FastAPI, LangChain (Groq/NVIDIA), and Supabase. 

Unlike traditional chatbots that send the entire conversation to an LLM every turn, AURA uses a **deterministic agent pipeline**. This means we use fast, predictable Python logic (Regex/Dictionaries) to classify intents and trigger actions, and we only call the LLM once per turn strictly for text generation. 

## System Components

### 1. The FastAPI Server (`main.py`)
- **Role:** The entry point.
- **Responsibilities:**
  - Exposes REST endpoints for the chat widget (`/chat`) and the admin dashboard (`/admin/products`, `/admin/orders`).
  - Secures endpoints using Supabase Auth (JWT).
  - Handles file uploads and spins up background threads for document indexing.

### 2. The Orchestrator (`orchestrator.py`)
- **Role:** The traffic cop.
- **Responsibilities:**
  - Manages the lifecycle of a single `/chat` request.
  - Loads the user's session history.
  - Passes the user's message through the sequence of specialized agents.
  - Returns the final response and any triggered actions back to `main.py`.

### 3. The Agents (`agents.py`)
- **Role:** Specialized workers.
- **Components:**
  - **Intent Agent (Deterministic):** Uses Regex to figure out what the user wants (e.g., "refund", "general_query"). Very fast. No LLM.
  - **Retrieval Agent (RAG):** If the intent requires knowledge, this fetches relevant paragraphs from ChromaDB.
  - **Responder Agent (LLM):** The *only* agent that calls the Groq/NVIDIA API. It drafts a polite, helpful response using the retrieved context.
  - **Action Agent (Deterministic):** Maps intents and LLM responses to concrete backend functions (e.g., triggering a refund API).

### 4. Memory & State (`session_manager.py`)
- **Role:** The brain's short-term and long-term memory.
- **Responsibilities:**
  - Stores temporary workflow variables in-memory (e.g., `preferred_datetime`).
  - Persists the actual chat transcript to Supabase so conversations survive server restarts.

### 5. Retrieval-Augmented Generation (`rag.py`)
- **Role:** The librarian.
- **Responsibilities:**
  - Converts PDFs and DOCX files into mathematical vectors using local `sentence-transformers`.
  - Performs **Hybrid Search** (Vector similarity + BM25 keyword matching).
  - Returns the top relevant chunks to the Orchestrator.

### 6. Data Persistence (`supabase_client.py`)
- **Role:** The database connection.
- **Responsibilities:**
  - Talks to Supabase PostgreSQL for persistent data: Products, Orders, Policies, and Chat History.

## Architecture Diagram

```mermaid
graph TD
    User([User / Chat Widget]) -->|HTTP POST /chat| Main(FastAPI main.py)
    
    Main -->|process_message()| Orch(Orchestrator)
    
    subgraph "Agent Pipeline (orchestrator.py)"
        Orch -->|1. Predict Intent| IA[Intent Agent]
        IA -->|2. Fetch Context| RA[Retrieval Agent (RAG)]
        RA -->|3. Draft Response| Resp[Responder Agent (LLM)]
        Resp -->|4. Trigger API| AA[Action Agent]
    end
    
    RA -.->|Queries| Chroma[(ChromaDB Local)]
    Resp -.->|Calls| LLM[Groq / NVIDIA API]
    AA -.->|Reads/Writes| Supabase[(Supabase PG)]
    
    Main -->|Background Task| Indexing[PDF/DOCX Ingestion]
    Indexing -.->|Extracts & Embeds| Chroma
```

## Key Design Decisions

1. **Why Local Embeddings?**
   We use `sentence-transformers` locally instead of OpenAI because it's free, faster (no network latency), and keeps proprietary manuals completely private.
2. **Why Single LLM Call?**
   Earlier versions used an LLM to predict intent and an LLM to verify the response. This was slow. Now, intent prediction is deterministic, reducing latency and cost.
3. **Why Supabase + ChromaDB?**
   Supabase handles structured relational data (Orders, Users) perfectly. ChromaDB is optimized specifically for fast vector math on unstructured data (PDFs).
