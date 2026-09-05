"""
All network calls to Gemini live here, and nowhere else in the codebase.
Every public function fails soft: on any error (missing key, network issue,
quota, malformed response) it returns None and logs a one-line reason rather
than raising. Callers (report_builder, payee_normalizer) are written to fall
back to deterministic behaviour when a call returns None. This is the
"graceful behaviour when a model call fails" the brief asks for.
"""
import logging
from src import config

logger = logging.getLogger("gemini_client")

_genai = None
_client_ready = False

if config.GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=config.GEMINI_API_KEY)
        _genai = genai
        _client_ready = True
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("Gemini SDK unavailable/misconfigured: %s", e)
        _client_ready = False


def is_available() -> bool:
    return _client_ready


def generate_text(prompt: str, max_output_tokens: int = 1024) -> str | None:
    """Returns generated text, or None if the LLM call could not be completed."""
    if not _client_ready:
        return None
    try:
        model = _genai.GenerativeModel(config.LLM_MODEL)
        resp = model.generate_content(
            prompt,
            generation_config={"max_output_tokens": max_output_tokens, "temperature": 0.2},
        )
        text = getattr(resp, "text", None)
        return text.strip() if text else None
    except Exception as e:
        logger.warning("Gemini generate_content failed: %s", e)
        return None


def embed_text(text: str) -> list | None:
    """Returns an embedding vector for a single string, or None on failure."""
    if not _client_ready:
        return None
    try:
        result = _genai.embed_content(model=f"models/{config.EMBED_MODEL}", content=text)
        return result.get("embedding")
    except Exception as e:
        logger.warning("Gemini embed_content failed: %s", e)
        return None


def embed_batch(texts: list[str]) -> list | None:
    """Best-effort batch embedding. Returns a list of vectors aligned to `texts`,
    or None entirely if the batch fails (caller should fall back for all of them)."""
    if not _client_ready:
        return None
    vectors = []
    for t in texts:
        v = embed_text(t)
        if v is None:
            return None
        vectors.append(v)
    return vectors
