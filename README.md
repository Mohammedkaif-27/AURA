# AURA — AI-Powered Unified Response Agent
## Intelligent Customer Support System with RAG, Multi-Agent Orchestration & Automated Actions

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=black" />
  <img src="https://img.shields.io/badge/FastAPI-0.104+-009688?style=for-the-badge&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/Supabase-PostgreSQL-3FCF8E?style=for-the-badge&logo=supabase&logoColor=white" />
  <img src="https://img.shields.io/badge/ChromaDB-Vector_Store-FF6F61?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Groq-LPU_Inference-F55036?style=for-the-badge" />
  <img src="https://img.shields.io/badge/HuggingFace-Local_Models-FFD21E?style=for-the-badge&logo=huggingface&logoColor=black" />
</p>

---

AURA is a production-grade, AI-powered customer support platform that goes far beyond a simple chatbot. It combines **Retrieval-Augmented Generation (RAG)** with a **multi-agent orchestration pipeline** and **deterministic action execution** to provide accurate, context-grounded answers from product manuals while autonomously processing refunds, replacements, and service bookings — all enforced by configurable business policies.

### ✨ Key Highlights

- 🤖 **Multi-Agent Pipeline** — Intent → RAG → Responder → Action → Execution (only 1 LLM call per request)
- 📄 **Knowledge-Grounded Answers** — Hybrid BM25 + Vector search with Reciprocal Rank Fusion eliminates hallucination
- ⚡ **Sub-2s Response Times** — Groq LPU inference + deterministic intent classification + LLM response caching
- 🔒 **Deterministic Policy Enforcement** — Refund/replacement windows enforced programmatically, not by the LLM
- 📧 **Automated Email Notifications** — Transactional emails via SMTP or Resend API on every action
- 🛡️ **Enterprise Auth** — Supabase Auth with JWT validation, Row-Level Security (RLS), and role-based admin access
- 📊 **Full Admin Dashboard** — Manage products, orders, policies, knowledge base, and monitor live conversations

---

## System Architecture Design

Below is the comprehensive architectural design for the AURA platform.

---

### 1. Component Diagram

This diagram illustrates the high-level boundaries between the Customer Frontend, Admin Dashboard, API Gateway, Agent Orchestration Layer, Data Storage, and External Providers.

```mermaid
graph TD
    subgraph Customer_Frontend ["Customer Frontend ‒ React + Vite"]
        UI_Chat[Chat Interface]
        UI_Auth[Auth / Login]
        UI_History[Session History]
    end

    subgraph Admin_Dashboard ["Admin Dashboard ‒ React + Vite"]
        Admin_Products[Product Management]
        Admin_Orders[Order Management]
        Admin_Knowledge[Knowledge Base]
        Admin_Policies[Policy Engine]
        Admin_Live[Live Chat Monitor]
    end

    subgraph API_Gateway ["FastAPI Gateway"]
        API_AuthMiddleware[JWT Validation Middleware]
        API_Chat[Chat Router]
        API_Admin[Admin Router]
        API_Upload[Document Upload Router]
        API_Sessions[Session Router]
    end

    subgraph Orchestration ["Multi-Agent Orchestration Layer"]
        Agent_Intent[Intent Agent ‒ Deterministic]
        Agent_Retrieval[Retrieval Agent ‒ Hybrid Search]
        Agent_Responder[Responder Agent ‒ LLM]
        Agent_Verifier[Verifier Agent ‒ Optional]
        Agent_Action[Action Agent ‒ Deterministic]
        Agent_Execution[Execution Engine]
    end

    subgraph Data_Layer ["Data and Storage"]
        DB_Supabase[("Supabase PostgreSQL")]
        DB_Chroma[("ChromaDB Vector Store")]
        Storage_Docs[("Supabase Blob Storage")]
    end

    subgraph External_APIs ["External Services"]
        LLM_Groq[Groq LPU ‒ Llama 3.3 70B]
        LLM_NVIDIA[NVIDIA NIM ‒ Fallback]
        Email_SMTP[SMTP / Resend Email]
    end

    Customer_Frontend --> API_Gateway
    Admin_Dashboard --> API_Gateway

    API_Gateway --> Orchestration

    Agent_Retrieval --> DB_Chroma
    Agent_Responder --> LLM_Groq
    Agent_Responder -.-> LLM_NVIDIA
    Agent_Execution --> DB_Supabase
    Agent_Execution --> Email_SMTP

    API_Upload --> Storage_Docs
    API_Upload --> DB_Chroma

    API_Admin --> DB_Supabase
    API_Sessions --> DB_Supabase
```

---

### 2. Data Flow Diagram

Visualizes the complete lifecycle of a user message through the multi-agent pipeline.

```mermaid
graph LR
    User(["Customer"]) -->|1. Sends Message| API(FastAPI)
    API -->|2. Load/Create Session| SessionMgr(Session Manager)
    SessionMgr -->|3. Check for Order ID| OrderLookup(Order Lookup)
    OrderLookup -->|4. Fetch from DB| Supabase[("Supabase")]

    API -->|5. Classify Intent| IntentAgent["Intent Agent Regex ‒ No LLM"]
    IntentAgent -->|6. Should Use RAG?| RAGDecision{RAG Needed?}

    RAGDecision -->|Yes| QueryExp["Query Expansion LLM-assisted"]
    QueryExp -->|7. Hybrid Search| BM25["BM25 Keyword Index"]
    QueryExp -->|7. Hybrid Search| VectorDB["ChromaDB via Local Model"]
    BM25 -->|8. Reciprocal Rank Fusion| Fusion[RRF Merger]
    VectorDB -->|8. Reciprocal Rank Fusion| Fusion
    Fusion -->|9. Rank Top-K| RerankerNode["RRF Weighted Ranking"]

    RAGDecision -->|No ‒ Greeting/Short| DirectResp[Skip to Responder]

    RerankerNode -->|10. Context + Policies| Responder["Responder Agent ‒ 1 LLM Call"]
    DirectResp --> Responder
    Responder -->|11. Decide Action| ActionAgent["Action Agent ‒ Deterministic"]
    ActionAgent -->|12. Execute| Executor[Action Executor]
    Executor -->|13. Notify| EmailService["Email Service"]
    Executor -->|14. Persist| Supabase
    Executor -->|15. Return Response| User
```

---

### 3. Sequence Diagram — Full Agent Pipeline

Demonstrates the real-time interaction for a customer requesting a refund with policy enforcement.

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant FastAPI
    participant SessionMgr
    participant IntentAgent
    participant RAG
    participant PolicyEngine
    participant Responder
    participant ActionAgent
    participant Executor
    participant Supabase
    participant Email

    User->>Frontend: I want a refund for ORD201
    Frontend->>FastAPI: POST /chat with message, session_id, JWT
    FastAPI->>FastAPI: Validate JWT Token
    FastAPI->>SessionMgr: get_session with session_id
    SessionMgr->>Supabase: Fetch/Create Session
    FastAPI->>FastAPI: Extract Order ID ORD201
    FastAPI->>Supabase: Fetch Order Details
    Supabase-->>FastAPI: product, purchase_date, warranty

    FastAPI->>IntentAgent: Classify Intent via Regex
    IntentAgent-->>FastAPI: refund

    FastAPI->>RAG: Hybrid Search BM25 + Vector
    RAG-->>FastAPI: Top-5 Reranked Chunks

    FastAPI->>Supabase: Fetch Policies
    Supabase-->>FastAPI: Refund Policy Rules

    FastAPI->>PolicyEngine: Check window_days
    alt Purchase older than 30 days
        PolicyEngine-->>FastAPI: REJECTED Policy Violation
        FastAPI-->>Frontend: Sorry refund window has expired
    else Within Policy Window
        FastAPI->>Responder: Generate Response with Context + Session
        Responder-->>FastAPI: Draft Response

        FastAPI->>ActionAgent: Map Intent to Action
        ActionAgent-->>FastAPI: initiate_refund

        FastAPI->>Executor: Execute Refund
        Executor->>Supabase: Insert Refund Record
        Executor->>Email: Send Confirmation Email
        Email-->>Executor: Sent

        FastAPI-->>Frontend: Response + Action Log
        Frontend-->>User: Display Answer + Refund Confirmation
    end
```

---

### 4. Database Schema (ER Diagram)

Entity-Relationship diagram representing the relational data in Supabase PostgreSQL. Vector embeddings reside in ChromaDB.

```mermaid
erDiagram
    USERS ||--o{ CHAT_SESSIONS : creates
    USERS ||--o{ ORDERS : places
    CHAT_SESSIONS ||--o{ CHAT_MESSAGES : contains
    ORDERS ||--o{ REFUNDS : triggers
    ORDERS ||--o{ REPLACEMENTS : triggers
    ORDERS ||--o{ SERVICE_BOOKINGS : triggers
    PRODUCTS ||--o{ ORDERS : referenced_in
    PRODUCTS ||--o{ KNOWLEDGE_BASE : documented_by

    USERS {
        uuid id PK
        string email
        string encrypted_password
        jsonb user_metadata
        timestamp created_at
    }

    PRODUCTS {
        text id PK
        text name
        numeric price
        text brand
        text category
        text_array aliases
        int warranty_years
        text manual_url
    }

    ORDERS {
        text id PK
        text customer_name
        text customer_phone
        text product_id FK
        text product_name
        text status
        date purchase_date
        int warranty_years
        text serial_number
    }

    POLICIES {
        text id PK
        text policy_type
        text scope
        text category
        jsonb rules
        text description
    }

    KNOWLEDGE_BASE {
        bigint id PK
        text file_name
        text bucket_path
        text document_type
        text status
        int chunks_count
        timestamp last_indexed
    }

    CHAT_SESSIONS {
        bigint id PK
        text session_id UK
        uuid user_id FK
        text title
        text status
    }

    CHAT_MESSAGES {
        bigint id PK
        text session_id FK
        text role
        text content
        jsonb sources
    }

    REFUNDS {
        bigint id PK
        text refund_id UK
        text order_id FK
        text status
    }

    REPLACEMENTS {
        bigint id PK
        text replacement_id UK
        text order_id FK
        text status
    }

    SERVICE_BOOKINGS {
        bigint id PK
        text service_id UK
        text order_id FK
        text scheduled_date
        text time_slot
    }
```

---

### 5. API Reference

> **Auth:** All endpoints (except `/health`) require a Bearer JWT obtained from Supabase Auth. Admin endpoints additionally require `is_admin` user metadata or inclusion in the `ADMIN_EMAILS` allowlist.

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/chat` | User | Send a message through the agent pipeline |
| `GET` | `/sessions` | User | List all chat sessions for the authenticated user |
| `GET` | `/sessions/{id}/messages` | User | Retrieve message history for a session |
| `PUT` | `/sessions/{id}` | User | Update session title |
| `DELETE` | `/sessions/{id}` | User | Delete a chat session |
| `POST` | `/admin/upload` | Admin | Upload PDF/DOCX/PPTX to the knowledge base |
| `GET` | `/admin/upload/status/{job_id}` | Admin | Check document ingestion status |
| `GET` | `/admin/products` | Admin | List all products |
| `POST` | `/admin/products` | Admin | Create a new product |
| `PUT` | `/admin/products/{id}` | Admin | Update a product |
| `DELETE` | `/admin/products/{id}` | Admin | Delete a product |
| `GET` | `/admin/orders` | Admin | List all orders |
| `POST` | `/admin/orders` | Admin | Create an order |
| `PUT` | `/admin/orders/{id}` | Admin | Update an order |
| `DELETE` | `/admin/orders/{id}` | Admin | Delete an order |
| `POST` | `/admin/import-orders` | Admin | Bulk import orders from XLSX/JSON |
| `GET` | `/admin/policies` | Admin | List all policies |
| `POST` | `/admin/policies` | Admin | Create a policy |
| `PUT` | `/admin/policies/{id}` | Admin | Update a policy |
| `DELETE` | `/admin/policies/{id}` | Admin | Delete a policy |
| `GET` | `/admin/knowledge` | Admin | List all knowledge documents |
| `DELETE` | `/admin/knowledge/{id}` | Admin | Delete a knowledge document |
| `GET` | `/admin/live/sessions` | Admin | List active chat sessions (live monitor) |
| `GET` | `/admin/live/sessions/{id}` | Admin | Get messages for a live session |

---

### 6. Deployment Architecture

Containerized deployment with managed cloud services for scalability and zero-downtime redeploys.

```mermaid
graph TD
    subgraph Client ["Client Devices"]
        Browser["Web Browser"]
    end

    subgraph Frontend ["Local Frontend Server"]
        FE_Customer["Customer Chat App ‒ /frontend"]
        FE_Admin["Admin Dashboard ‒ /admin"]
    end

    subgraph Backend ["Local Backend Server (FastAPI)"]
        FastAPI_App["FastAPI Server uvicorn"]
        OrchestratorNode["Agent Orchestrator"]
        RAG_Engine["RAG Engine"]
        ChromaDB_Vol[("ChromaDB Vector Store")]
    end

    subgraph Supabase_Cloud ["Supabase Cloud ‒ Managed"]
        PostgreSQL[("PostgreSQL")]
        Auth["Auth Service"]
        BlobStorage[("Blob Storage ‒ Document PDFs")]
    end

    subgraph External ["External APIs"]
        Groq["Groq LPU Llama 3.3 70B"]
        EmailProvider["SMTP / Resend"]
    end

    Browser --> FE_Customer
    Browser --> FE_Admin
    FE_Customer -->|HTTP| FastAPI_App
    FE_Admin -->|HTTP| FastAPI_App
    FastAPI_App --> OrchestratorNode
    OrchestratorNode --> RAG_Engine
    RAG_Engine --> ChromaDB_Vol
    FastAPI_App --> PostgreSQL
    FastAPI_App --> Auth
    FastAPI_App --> BlobStorage
    OrchestratorNode --> Groq
    FastAPI_App --> EmailProvider
```

---

### 7. Folder Structure

```text
AURA/
├── backend/                          # Python FastAPI Backend
│   ├── __init__.py                   # Package marker
│   ├── main.py                       # FastAPI app entry point, all routes
│   ├── orchestrator.py               # Multi-agent pipeline coordinator
│   ├── agents.py                     # Intent, Retrieval, Responder, Verifier, Action agents
│   ├── rag.py                        # RAG engine (HF API embeddings, ChromaDB, BM25, RRF)
│   ├── llm_client.py                 # Unified LLM interface (Groq/NVIDIA) with caching
│   ├── session_manager.py            # Chat session state and Supabase persistence
│   ├── order_lookup.py               # Order ID extraction and DB lookup
│   ├── supabase_client.py            # Supabase wrapper (products, orders, policies, RLS)
│   ├── notifications.py              # Email notification service (SMTP/Resend)
│   ├── chroma_db/                    # ChromaDB persistent vector storage
│   └── data/                         # Local action logs (refunds, replacements, bookings)
│
├── frontend/                         # Customer-Facing Chat (React 19 + Vite)
│   ├── src/
│   │   ├── App.jsx                   # Root component with auth routing
│   │   ├── api.js                    # Backend API client functions
│   │   ├── main.jsx                  # React entry point
│   │   ├── index.css                 # Global styles (design system, responsive, animations)
│   │   ├── components/
│   │   │   ├── Auth.jsx              # Login / signup form
│   │   │   ├── ChatWindow.jsx        # Main chat UI with session sidebar
│   │   │   ├── MessageBubble.jsx     # Individual message renderer
│   │   │   ├── ActionCard.jsx        # Action result display cards
│   │   │   ├── ConfirmModal.jsx      # Bottom-sheet modal (mobile) / centered (desktop)
│   │   │   ├── SourceChip.jsx        # Source citation chips
│   │   │   └── TypingIndicator.jsx   # Bot typing animation
│   │   └── lib/
│   │       └── supabase.js           # Supabase client initialization
│   └── index.html
│
├── admin/                            # Admin Dashboard (React 19 + Vite)
│   ├── src/
│   │   ├── App.jsx                   # Root with sidebar navigation
│   │   ├── main.jsx                  # React entry point
│   │   ├── index.css                 # Admin theme styles
│   │   ├── components/
│   │   │   ├── Auth.jsx              # Admin login
│   │   │   ├── Sidebar.jsx           # Navigation sidebar
│   │   │   ├── StatCard.jsx          # Dashboard metric cards
│   │   │   ├── UploadZone.jsx        # Drag-and-drop file uploader
│   │   │   ├── ChatFeed.jsx          # Live chat message feed
│   │   │   └── ConfirmModal.jsx      # Delete confirmation modal
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx         # Overview stats + order import
│   │   │   ├── Knowledge.jsx         # Knowledge base management
│   │   │   ├── Inventory.jsx         # Product CRUD
│   │   │   ├── Orders.jsx            # Order CRUD + filtering
│   │   │   ├── Policies.jsx          # Policy engine configuration
│   │   │   └── LiveCenter.jsx        # Real-time chat monitoring
│   │   └── lib/
│   │       └── supabase.js           # Supabase client initialization
│   └── index.html
│
├── .env.example                      # Environment variable template
├── Dockerfile                        # Production container (Python 3.11 slim)
├── .dockerignore                     # Docker build exclusions
├── requirements.txt                  # Python dependencies
├── supabase_schema.sql               # Complete idempotent DB schema
└── README.md                         # This file
```

---

### 8. Design Justifications

**1. Multi-Agent Architecture with Minimal LLM Calls**

The system employs a pipeline of specialized agents, but is architected to use only **1 LLM call per user message** (the Responder). Intent classification is fully deterministic (regex/keyword), action mapping is a static dictionary lookup, and confirmation messages use predefined templates. This reduces latency by ~70% and cost by ~75% compared to naive multi-LLM-call architectures.

**2. Hybrid RAG with 4-Stage Retrieval**

Rather than relying solely on vector similarity, AURA implements a sophisticated 4-stage retrieval pipeline:
1. **LLM-based Query Expansion** — Rewrites the user query with alternative terminology
2. **BM25 Keyword Search** — Captures exact term matches that embeddings might miss
3. **Vector Similarity Search** — ChromaDB cosine similarity over local BGE embeddings
4. **Reciprocal Rank Fusion (RRF)** — Merges BM25 and vector results into a weighted unified ranking

This fully local approach guarantees absolute data privacy and zero API latency for embeddings, while maintaining robust retrieval quality.

**3. Deterministic Policy Enforcement**

Business-critical rules (refund window, replacement eligibility) are **never delegated to the LLM**. The orchestrator programmatically checks `purchase_date` against `policy.rules.window_days` and short-circuits the pipeline with a rejection message if the policy is violated. This eliminates the risk of an LLM hallucinating a policy exception.

**4. Hallucination Reduction Framework**

Multiple layers of defense prevent the AI from fabricating information:
- **Grounded System Prompt** — The responder is explicitly instructed to only use provided context and cite sources
- **Citation Enforcement** — The prompt demands document name + page number for every factual claim
- **Optional Verifier Agent** — A second LLM pass (disabled by default) cross-checks the draft against the retrieved chunks
- **RAG Skip Logic** — Greetings and short acknowledgments bypass RAG entirely, preventing irrelevant context injection
- **LLM Response Cache** — Identical queries return cached responses, ensuring consistency

**5. Session-Aware Conversational State**

Unlike stateless Q&A bots, AURA maintains a rich session state that persists across messages:
- Extracts and remembers Order IDs from natural language ("my order ORD201")
- Carries forward customer name, product, warranty status, and pending actions
- Inherits intent from previous turns when the user provides follow-up information
- Persists sessions to Supabase so conversations survive server restarts

**6. Enterprise-Grade Security**

- **Supabase Auth** with email/password authentication and JWT tokens
- **Row-Level Security (RLS)** — User-scoped Supabase clients ensure customers can only see their own sessions
- **Admin Authorization** — Dual-layer check: `user_metadata.is_admin` flag + `ADMIN_EMAILS` env-var allowlist
- **Input Sanitization** — PyMuPDF explicitly prevents execution of embedded scripts in uploaded PDFs
- **Secrets Management** — All credentials injected via environment variables, never committed to git

**7. Multi-Format Document Ingestion**

The knowledge base accepts PDF, DOCX, and PPTX uploads with:
- **PyMuPDF** for superior PDF text extraction with reading-order preservation
- **Tesseract OCR** fallback for scanned/image-based PDF pages
- **Token-based chunking** with configurable size and overlap
- **Page-level metadata** — Every chunk carries its source filename and page number for precise citations
- **Background processing** — Ingestion runs in a ThreadPoolExecutor (3 workers) with progress tracking via job IDs

---

## Getting Started

### Prerequisites

- **Python 3.11+**
- **Node.js 18+**
- A free [Supabase](https://supabase.com) project
- A free [Groq](https://console.groq.com) API key

### 1. Clone and Configure

```bash
git clone https://github.com/your-username/AURA.git
cd AURA

# Create .env from template
cp .env.example .env
# Fill in your GROQ_API_KEY, SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY
```

### 2. Set Up the Database

Go to your Supabase Dashboard, open the SQL Editor, paste the contents of `supabase_schema.sql`, and run it.

### 3. Start the Backend

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

uvicorn backend.main:app --reload
```
The API will be live at `http://localhost:8000`.

### 4. Start the Customer Frontend

```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173`.

### 5. Start the Admin Dashboard

```bash
cd admin
npm install
npm run dev
```
Open `http://localhost:5174`.

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **LLM Inference** | Groq (Llama 3.3 70B) | Ultra-fast response generation via LPU |
| **LLM Fallback** | NVIDIA NIM | Secondary provider for resilience |
| **Embeddings** | sentence-transformers (BGE) | Local, private semantic embeddings |
| **Reranker** | local cross-encoder | High accuracy post-retrieval reranking |
| **Vector Store** | ChromaDB | Persistent vector database |
| **Keyword Search** | BM25 (rank-bm25) | Complementary lexical retrieval |
| **Database** | Supabase PostgreSQL | Relational data + Auth + Blob Storage |
| **Backend** | FastAPI + Uvicorn | Async Python API server |
| **Frontend** | React 19 + Vite | Customer chat and Admin dashboard |
| **Styling** | Tailwind CSS v4 | Utility-first CSS framework |
| **Email** | SMTP / Resend | Transactional notification delivery |
| **Containerization** | Docker | Production deployment packaging |


---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `LLM_PROVIDER` | Yes | `groq` (default) or `nvidia` |
| `GROQ_API_KEY` | Yes | Your Groq API key |
| `SUPABASE_URL` | Yes | Your Supabase project URL |
| `SUPABASE_ANON_KEY` | Yes | Supabase anon/public key |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Supabase service role key |
| `EMBEDDING_MODEL` | No | Default: `BAAI/bge-base-en-v1.5` |
| `RERANKER_MODEL` | No | Default: `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| `ADMIN_API_KEY` | Yes (for rebuild) | Secure random string for admin API actions |
| `ENABLE_REBUILD_ENDPOINT` | No | Default: `false`. Set to `true` to allow vector DB rebuilds |
| `SMTP_HOST` | No | Email server host (default: `smtp.gmail.com`) |
| `SMTP_USERNAME` | No | Email account username |
| `SMTP_PASSWORD` | No | Email account app password |
| `ADMIN_EMAILS` | No | Comma-separated admin email allowlist |
| `ENABLE_VERIFIER` | No | Enable response verification (default: `false`) |
| `ENABLE_QUERY_EXPANSION` | No | Enable LLM query expansion (default: `true`) |
| `ENABLE_HYBRID_SEARCH` | No | Enable BM25+Vector hybrid (default: `true`) |

---

## License

This project is proprietary. All rights reserved.

---

<p align="center">
  Built with care by <strong>Mohammed Kaif</strong>
</p>
