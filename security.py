import os
from fastapi import Header, HTTPException

API_KEY = os.getenv("API_KEY")
REQUIRE = os.getenv("REQUIRE_API_KEY", "0") == "1"

def api_guard(x_api_key: str | None = Header(None)):
    """Minimal API Key guard for FastAPI routes.

    Behavior:
      - If REQUIRE_API_KEY != '1', this guard is a no-op (backward-compatible).
      - Otherwise, it requires header X-API-Key to match the server's API_KEY.
    """
    if not REQUIRE:
        return
    if not API_KEY or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
