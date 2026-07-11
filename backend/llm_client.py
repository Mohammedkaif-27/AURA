"""
AURA LLM Client — Unified interface for Groq (primary) and NVIDIA NIM (fallback).

Switch providers by changing LLM_PROVIDER in .env (no code changes needed).
Includes exponential-backoff retry for rate limits and an optional response cache.

OPTIMIZED:
- Singleton Groq/NVIDIA client (created once, reused across all requests)
- Thread-safe initialization with locks
- Response caching with LRU-style eviction
"""

import os
import time
import hashlib
import json
import logging
import threading
from typing import List, Dict, Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────
PROVIDER = os.getenv("LLM_PROVIDER", "groq")  # "groq" | "nvidia"
MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))
CACHE_ENABLED = os.getenv("LLM_CACHE_ENABLED", "true").lower() == "true"

# ── In-memory response cache ────────────────────────────────────────
_response_cache: Dict[str, str] = {}
_CACHE_MAX_SIZE = 500

# ── Singleton clients ───────────────────────────────────────────────
_groq_client = None
_nvidia_client = None
_init_lock = threading.Lock()
_initialized = False


def _cache_key(messages: List[Dict], model: str, temperature: float) -> str:
    """Deterministic hash for a request."""
    payload = json.dumps({"m": messages, "model": model, "t": temperature}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _get_cached(key: str) -> Optional[str]:
    if CACHE_ENABLED and key in _response_cache:
        logger.debug("LLM cache hit")
        return _response_cache[key]
    return None


def _set_cached(key: str, value: str):
    if CACHE_ENABLED:
        if len(_response_cache) >= _CACHE_MAX_SIZE:
            # Evict oldest ~10%
            keys_to_evict = list(_response_cache.keys())[: _CACHE_MAX_SIZE // 10]
            for k in keys_to_evict:
                _response_cache.pop(k, None)
        _response_cache[key] = value


# ── Client initialization ───────────────────────────────────────────

def initialize_llm_client() -> bool:
    """Initialize the LLM client singleton during startup.
    
    Thread-safe. Returns True if client was successfully created.
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


# ── Provider implementations ─────────────────────────────────────────

def _call_groq(messages: List[Dict], model: str, temperature: float, max_tokens: int) -> str:
    """Call Groq API using the singleton client."""
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
    """Call NVIDIA NIM API using the singleton client."""
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


# ── Public API ───────────────────────────────────────────────────────

def get_completion(
    messages: List[Dict],
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 1024,
) -> str:
    """
    Send a chat completion request to the configured LLM provider.

    Supports Groq (default) and NVIDIA NIM — controlled by LLM_PROVIDER env var.
    Retries with exponential backoff on rate-limit / transient errors.
    Caches responses for identical requests (helps free-tier rate limits).
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

            if is_retryable and attempt < MAX_RETRIES * 3: # Allow more retries for long rate limits
                wait = 2 ** attempt
                # Parse exact wait time if provided (e.g. "try again in 1m3.9s" or "3m50s" or "4.5s")
                import re
                match = re.search(r"try again in (?:(\d+)m)?([\d\.]+)s", error_str)
                if match:
                    mins = int(match.group(1)) if match.group(1) else 0
                    secs = float(match.group(2))
                    wait = (mins * 60) + secs + 1.0 # Add 1s buffer
                
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
