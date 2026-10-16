"""API-key auth. Demo-grade: one shared key, constant-time compare.

Production path on Azure: swap this dependency for Entra ID (OAuth2) —
route code doesn't change because auth is a dependency, not inline logic.
"""
import hmac
import os
from fastapi import Header, HTTPException

API_KEY = os.environ.get("DATAPILOT_API_KEY", "demo-key-123")


def require_key(x_api_key: str | None = Header(default=None)) -> str:
    if not x_api_key or not hmac.compare_digest(x_api_key, API_KEY):
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key")
    return x_api_key
