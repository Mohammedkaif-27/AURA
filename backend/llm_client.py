"""
AURA Backend — LLM Client

Purpose:
    Unified interface for calling Large Language Models.
    Currently supports Groq (primary) and NVIDIA NIM (fallback).
    Switch providers by changing LLM_PROVIDER in .env — no code
    changes needed.

Responsibilities:
    - Initialize an LLM client once (singleton pattern)
    - Route requests to the correct provider
    - Retry with exponential backoff on rate-limit errors
    - Cache identical requests to reduce API calls

Workflow:
    get_completion()
        │
        ├─ Check response cache
        │
        ├─ Route to _call_groq() or _call_nvidia()
        │
        ├─ Retry on 429 / 503 / timeout
        │
        └─ Cache and return result

Used By:
    agents.py  (every agent calls get_completion)

Depends On:
    groq, openai (for NVIDIA NIM)

Related Files:
    config.py       — LLM_PROVIDER, model names
    agents.py       — builds prompts, calls get_completion
    orchestrator.py — routes user messages through agents
"""

import os
import re
import time
import hashlib
import json
import logging
import threading
from typing import List, Dict, Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# ==========================================================
# CONFIGURATION
# ==========================================================
PROVIDER = os.getenv("LLM_PROVIDER", "groq")      # "groq" | "nvidia"
MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))
CACHE_ENABLED = os.getenv("LLM_CACHE_ENABLED", "true").lower() == "true"


# ==========================================================
# RESPONSE CACHE
# ==========================================================
# Why?  On free-tier LLM APIs, rate limits are strict.  Caching
# identical requests avoids redundant API calls and speeds up
# repeated questions (e.g. "what is your return policy?").
_response_cache: Dict[str, str] = {}
_CACHE_MAX_SIZE = 500


# ==========================================================
# SINGLETON CLIENTS
# ==========================================================
# Why singletons?  Creating an API client on every request wastes
# time and memory.  We create ONE client at startup and reuse it.
_groq_client = None
_nvidia_client = None
_init_lock = threading.Lock()
_initialized = False


# ==========================================================
# CACHE HELPERS
# ==========================================================

def _cache_key(messages: List[Dict], model: str, temperature: float) -> str:
    """Deterministic hash for a request (same input → same cache key)."""
    payload = json.dumps({"m": messages, "model": model, "t": temperature}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _get_cached(key: str) -> Optional[str]:
    """Return cached response if it exists, else None."""
    if CACHE_ENABLED and key in _response_cache:
        logger.debug("LLM cache hit")
        return _response_cache[key]
    return None


def _set_cached(key: str, value: str):
    """Store a response in the cache, evicting oldest entries if full."""
    if CACHE_ENABLED:
        if len(_response_cache) >= _CACHE_MAX_SIZE:
            keys_to_evict = list(_response_cache.keys())[: _CACHE_MAX_SIZE // 10]
            for k in keys_to_evict:
                _response_cache.pop(k, None)
        _response_cache[key] = value


# ==========================================================
# CLIENT INITIALIZATION
# ==========================================================

def initialize_llm_client() -> bool:
    """
    Initialize the LLM client singleton during startup.

    Why?
        The client must be created before any agent can call the LLM.
        This runs once inside main.py's startup event so that the
        first user request doesn't pay the initialization cost.

    Called By:  main.py (startup)
    Returns:    True if the client was successfully created.
    """
    global _groq_client, _nvidia_client, _initialized

    with _init_lock:
        if _initialized:
            return True

        provider = PROVIDER.lower()

        try:
            if provider == "groq":
                from groq import Groq
                api_key = os.getenv("GROQ_API_KEY")
                if not api_key:
                    logger.error("GROQ_API_KEY missing — LLM calls will fail")
                    return False
                _groq_client = Groq(api_key=api_key)
                logger.info("Groq client initialized (singleton)")

            elif provider == "nvidia":
                import openai
                api_key = os.getenv("NVIDIA_API_KEY")
                if not api_key:
                    logger.error("NVIDIA_API_KEY missing — LLM calls will fail")
                    return False
                _nvidia_client = openai.OpenAI(
                    base_url="https://integrate.api.nvidia.com/v1",
                    api_key=api_key,
                )
                logger.info("NVIDIA NIM client initialized (singleton)")

            else:
                logger.error(f"Unknown LLM_PROVIDER: '{provider}'")
                return False

            _initialized = True
            return True

        except Exception as e:
            logger.error(f"Failed to initialize LLM client: {e}")
            return False


# ==========================================================
# PROVIDER IMPLEMENTATIONS
# ==========================================================
# Why two separate functions?
# Groq uses its own SDK.  NVIDIA NIM uses the OpenAI-compatible SDK.
# Both return the same thing: a string response.

def _call_groq(messages: List[Dict], model: str, temperature: float, max_tokens: int) -> str:
    """Call Groq LPU inference API."""
    global _groq_client

    if _groq_client is None:
        initialize_llm_client()
    if _groq_client is None:
        raise RuntimeError("Groq client not initialized. Check GROQ_API_KEY.")

    model = model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    resp = _groq_client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content


def _call_nvidia(messages: List[Dict], model: str, temperature: float, max_tokens: int) -> str:
    """Call NVIDIA NIM API (OpenAI-compatible)."""
    global _nvidia_client

    if _nvidia_client is None:
        initialize_llm_client()
    if _nvidia_client is None:
        raise RuntimeError("NVIDIA client not initialized. Check NVIDIA_API_KEY.")

    model = model or os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct")

    resp = _nvidia_client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content


# ==========================================================
# PUBLIC API  —  get_completion()
# ==========================================================

def get_completion(
    messages: List[Dict],
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 1024,
) -> str:
    """
    Send a chat-completion request to the configured LLM provider.

    Why?
        Every agent (intent, retrieval, responder, verifier) needs to
        call the LLM.  This function is the single gateway — it handles
        caching, retries, and provider routing so agents don't have to.

    Called By:  agents.py (intent_agent, retrieval_agent, responder_agent, etc.)
    Calls:     _call_groq() or _call_nvidia()
    Returns:   The LLM's text response (str).

    Workflow:
        1. Check cache → return immediately if hit
        2. Route to Groq or NVIDIA based on LLM_PROVIDER
        3. On rate-limit (429) or transient error → retry with backoff
        4. Cache the successful response
        5. Return the result
    """
    resolved_model = model or ""
    cache_k = _cache_key(messages, resolved_model, temperature)
    cached = _get_cached(cache_k)
    if cached is not None:
        return cached

    provider = PROVIDER.lower()
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if provider == "groq":
                result = _call_groq(messages, model, temperature, max_tokens)
            elif provider == "nvidia":
                result = _call_nvidia(messages, model, temperature, max_tokens)
            else:
                raise ValueError(
                    f"Unknown LLM_PROVIDER: '{provider}'. "
                    f"Supported values: 'groq', 'nvidia'."
                )

            _set_cached(cache_k, result)
            return result

        except Exception as e:
            last_error = e
            error_str = str(e).lower()

            # Retry on rate-limit or transient errors
            is_retryable = any(
                kw in error_str
                for kw in ["rate_limit", "rate limit", "429", "503", "timeout", "overloaded"]
            )

            if is_retryable and attempt < MAX_RETRIES * 3:
                wait = 2 ** attempt
                # Parse exact wait time if the API tells us (e.g. "try again in 1m3.9s")
                match = re.search(r"try again in (?:(\d+)m)?([\d\.]+)s", error_str)
                if match:
                    mins = int(match.group(1)) if match.group(1) else 0
                    secs = float(match.group(2))
                    wait = (mins * 60) + secs + 1.0

                logger.warning(
                    f"LLM call failed (attempt {attempt}), "
                    f"retrying in {wait:.1f}s: {e}"
                )
                time.sleep(wait)
            else:
                break

    raise RuntimeError(
        f"LLM call failed after {MAX_RETRIES} attempts "
        f"(provider={provider}): {last_error}"
    )
