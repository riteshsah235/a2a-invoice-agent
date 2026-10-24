import json
import hashlib
from typing import Any, Dict


def canonical_compact_json(obj: Any) -> str:
    """Serialize an object into recursively key-sorted compact JSON with no extraneous whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_fingerprint(obj: Any) -> str:
    """Compute the SHA-256 hex digest of the canonical compact JSON representation."""
    canonical_str = canonical_compact_json(obj)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


def derive_principal_id(bearer_token: str) -> str:
    """Derive a stable, isolated principal identifier from the Bearer token."""
    cleaned = bearer_token.strip()
    return f"principal_{hashlib.sha256(cleaned.encode('utf-8')).hexdigest()[:24]}"
