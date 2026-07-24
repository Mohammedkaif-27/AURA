# AURA Backend: A Guide for Students

> [!TIP]
> If you are new to Python, APIs, or AI Engineering, this document is for you. It explains the core concepts used in the AURA backend so you understand *why* the code is written the way it is.

## 1. What is FastAPI?

FastAPI is a modern Python web framework. It is used to build the API (Application Programming Interface) that allows our React frontend to talk to our Python backend.

**Why do we use it?**
- **Speed:** It's incredibly fast (based on Starlette and Pydantic).
- **Auto-Documentation:** It automatically generates an interactive documentation page (Swagger UI) so you can test your endpoints without writing any frontend code.
- **Async Support:** It handles multiple requests at the same time efficiently using `async` and `await`.

### Key Concepts in `main.py`
- `@app.get("/health")`: This is a "decorator". It tells FastAPI, "If a user visits the `/health` URL using a GET request, run the function below."
- **Pydantic Models (`BaseModel`):** Look at `class ChatRequest(BaseModel):`. This guarantees that when a user sends JSON to our server, it must have a `message` field that is a string. If they send a number instead, FastAPI automatically rejects it with an error. No manual validation needed!

## 2. What is RAG (Retrieval-Augmented Generation)?

Large Language Models (LLMs) like ChatGPT or Groq don't know about *your* specific company policies or product manuals. 

**RAG is a clever workaround:**
1. **Retrieve:** When a user asks a question, we search our private database (ChromaDB) for relevant paragraphs from our manuals.
2. **Augment:** We paste those paragraphs into the prompt alongside the user's question.
3. **Generate:** The LLM reads the paragraphs and generates an accurate answer based *only* on that context.

### What are Embeddings?
In `rag.py`, you'll see references to `sentence-transformers`. This converts sentences into massive arrays of numbers (vectors). 
- If two sentences mean the same thing, their vectors will be close together in space.
- This allows us to search for meaning, not just exact keywords. "My TV won't turn on" will match "Power troubleshooting steps" because their math aligns.

## 3. Why Deterministic Agents?

In many AI tutorials, you'll see people asking the LLM to do everything: "Figure out what the user wants, look up the database, format the answer, and send an email."

This is a bad idea for production because:
1. LLMs hallucinate (make things up).
2. LLMs are slow.
3. API calls cost money.

**The AURA approach (`agents.py`):**
We use standard Python (Regex, IF statements, string matching) to figure out what the user wants (e.g., "refund"). We call this **Deterministic** because it behaves the exact same way every single time. 

We *only* use the LLM at the very end to write a nice, human-sounding response. This makes AURA extremely fast and reliable.

## 4. What is Dependency Injection?

In `main.py`, you'll see functions with `Depends(...)`. 

```python
def admin_list_orders(user: dict = Depends(require_admin)):
```

This is FastAPI's dependency injection system. Before `admin_list_orders` is allowed to run, FastAPI will automatically run `require_admin` first. If `require_admin` fails (because the user isn't an admin or didn't provide a valid token), the request is blocked instantly. 

This keeps our code clean because we don't have to copy-paste security checks into every single function.

## 5. Environment Variables & `.env`

You'll notice we never put passwords or API keys directly in the code. Instead, we use `os.getenv("GROQ_API_KEY")`.

This reads from a hidden `.env` file on your computer. 
**Why?**
If you upload your code to GitHub, you don't want the whole world stealing your API keys and running up a $10,000 bill on your account. Always keep secrets out of the codebase!
