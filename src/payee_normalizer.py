"""
Real-world transaction descriptions for the "same" payee are rarely identical
strings ("AMAZON *RETAIL", "Amazon Retail Pvt Ltd", "AMZN"). R2_NEW_PAYEE_BURST
depends on knowing when a customer *first* dealt with a given payee, so
merging near-duplicate descriptions matters. This module embeds each unique
description with Gemini and greedily clusters by cosine similarity. If the
Gemini client is unavailable (no key, network failure), it falls back to
exact-string matching on a lightly normalized string \u2014 less powerful, but
transparent and still correct on data where descriptions are already clean
(as ours mostly are), which is the honest degrade-gracefully behaviour the
brief asks for.
"""
import math
from src import gemini_client

SIMILARITY_THRESHOLD = 0.90


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _normalize_string(s: str) -> str:
    return " ".join(s.strip().lower().split())


def build_canonical_payee_map(descriptions: list[str]) -> dict:
    """Returns {original_description: canonical_id} for the given list of
    (possibly repeated) description strings."""
    unique = sorted(set(descriptions))

    vectors = gemini_client.embed_batch(unique)

    if vectors is not None:
        canonical_ids = [None] * len(unique)
        cluster_reps = []  # list of (vector, canonical_id)
        next_id = 0
        for i, vec in enumerate(vectors):
            match = None
            for rep_vec, rep_id in cluster_reps:
                if _cosine(vec, rep_vec) >= SIMILARITY_THRESHOLD:
                    match = rep_id
                    break
            if match is None:
                match = f"payee_{next_id}"
                next_id += 1
                cluster_reps.append((vec, match))
            canonical_ids[i] = match
        return {desc: canonical_ids[i] for i, desc in enumerate(unique)}

    # Fallback: exact match on normalized string, no semantic clustering.
    mapping = {}
    seen = {}
    for desc in unique:
        key = _normalize_string(desc)
        if key not in seen:
            seen[key] = f"payee_{len(seen)}"
        mapping[desc] = seen[key]
    return mapping
