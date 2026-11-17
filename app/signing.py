"""Signed, tamper-proof tokens so sign-in and conversations survive restarts.

Azure Container Apps scales the app to zero when idle, which wipes process
memory and the container's local SQLite file. Instead of keeping sign-ins and
interview transcripts on the server, we hand them to the browser as HMAC-signed
tokens and verify them on every request. No database or storage account needed.

The key comes from SESSION_SECRET if set, otherwise it is derived from the
secrets the app already has (ACCESS_CODE and ANTHROPIC_API_KEY), so it stays the
same across restarts and changing the access code signs everyone out.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import zlib
from functools import lru_cache


@lru_cache(maxsize=1)
def _key() -> bytes:
    explicit = os.getenv("SESSION_SECRET", "")
    if explicit:
        return hashlib.sha256(b"podsim-explicit|" + explicit.encode()).digest()
    material = os.getenv("ACCESS_CODE", "") + "|" + os.getenv("ANTHROPIC_API_KEY", "")
    if material != "|":
        return hashlib.sha256(b"podsim-derived|" + material.encode()).digest()
    return secrets.token_bytes(32)  # local dev with no secrets: sessions last until restart


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _mac(purpose: str, payload: str) -> str:
    return _b64(hmac.new(_key(), f"{purpose}|{payload}".encode(), hashlib.sha256).digest())


def dumps(purpose: str, data: dict) -> str:
    payload = _b64(zlib.compress(json.dumps(data, separators=(",", ":")).encode(), 6))
    return payload + "." + _mac(purpose, payload)


def loads(purpose: str, token: str) -> dict | None:
    """Return the data if the token is genuine and was made for this purpose, else None."""
    try:
        payload, mac = token.rsplit(".", 1)
        if not hmac.compare_digest(mac, _mac(purpose, payload)):
            return None
        return json.loads(zlib.decompress(_unb64(payload), bufsize=1 << 16))
    except (ValueError, TypeError, zlib.error):
        return None
