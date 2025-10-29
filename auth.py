# auth.py
import os
from fastapi import Header, HTTPException

API_TOKEN = os.getenv("API_TOKEN", "")

async def require_bearer(authorization: str = Header("")):
    if not API_TOKEN:
        raise HTTPException(status_code=500, detail="Server misconfigured: API_TOKEN missing")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer")
    token = authorization.split(" ", 1)[1].strip()
    if token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")