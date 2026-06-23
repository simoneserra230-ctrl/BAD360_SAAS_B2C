"""
BAD360.ai — Auth Layer
Supabase JWT validation + demo token for local testing.

Endpoints:
  GET  /api/auth/me          — validate token, return user profile
  POST /api/auth/demo-login  — exchange demo credentials → mock token
  GET  /api/auth/status      — platform auth status (demo vs live)
"""

from __future__ import annotations
import os
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from jose import JWTError, jwt

logger = logging.getLogger("bad360.auth")
router = APIRouter(prefix="/api/auth", tags=["Auth"])

APP_SECRET     = os.getenv("APP_SECRET", "change-me-in-production-bad360")
SUPABASE_URL   = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY   = os.getenv("SUPABASE_SERVICE_KEY", "")
ALGORITHM      = "HS256"
DEMO_EXPIRY_H  = 24

# ── Demo accounts (for local/demo mode) ──────────────────────────────

DEMO_USERS = {
    "demo@bad360.ai":    {"password": "Demo2024!", "role": "bar_manager",      "name": "Demo User",    "hotel_id": "hotel-demo-001"},
    "test@bad360.ai":    {"password": "Test2024!", "role": "general_manager",  "name": "Test GM",      "hotel_id": "hotel-test-001"},
    "simone@bad360.ai":  {"password": "Bads2024!", "role": "owner",            "name": "Simone Serra", "hotel_id": "hotel-ss-001"},
    "admin@bad360.ai":   {"password": "Admin2024!","role": "platform_admin",   "name": "Admin",        "hotel_id": "hotel-admin"},
}


# ── Models ────────────────────────────────────────────────────────────

class DemoLoginRequest(BaseModel):
    email: str
    password: str

class UserProfile(BaseModel):
    id: str
    email: str
    name: str
    role: str
    hotel_id: str
    auth_mode: str  # "demo" | "supabase"
    expires_at: Optional[str] = None


# ── Token helpers ─────────────────────────────────────────────────────

def _create_demo_token(user: dict, email: str) -> str:
    payload = {
        "sub": email,
        "email": email,
        "name": user["name"],
        "role": user["role"],
        "hotel_id": user["hotel_id"],
        "auth_mode": "demo",
        "exp": datetime.utcnow() + timedelta(hours=DEMO_EXPIRY_H),
    }
    return jwt.encode(payload, APP_SECRET, algorithm=ALGORITHM)


def _decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, APP_SECRET, algorithms=[ALGORITHM])
    except JWTError:
        return None


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


# ── Dependency: get_current_user ─────────────────────────────────────

async def get_current_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_auth_token: Optional[str] = Header(None, alias="X-Auth-Token"),
) -> Optional[UserProfile]:
    """FastAPI dependency — validates JWT, returns UserProfile or None (demo fallback)."""
    token = _extract_bearer(authorization) or x_auth_token
    if not token:
        return None

    payload = _decode_token(token)
    if not payload:
        return None

    return UserProfile(
        id=payload.get("sub", "unknown"),
        email=payload.get("email", ""),
        name=payload.get("name", ""),
        role=payload.get("role", "user"),
        hotel_id=payload.get("hotel_id", "hotel-demo-001"),
        auth_mode=payload.get("auth_mode", "demo"),
        expires_at=str(datetime.utcfromtimestamp(payload["exp"])) if "exp" in payload else None,
    )


# ── Dependency: require_user (multi-tenant blindato) ─────────────────
# Primitiva di sicurezza riusabile da tutti i moduli gestionali: garantisce
# un utente autenticato e fornisce hotel_id SEMPRE dal token (mai dal client),
# così un cliente non può scrivere/leggere i dati di un altro hotel.

async def require_user(user: Optional[UserProfile] = Depends(get_current_user)) -> UserProfile:
    if not user:
        raise HTTPException(status_code=401, detail="Autenticazione richiesta")
    return user


# ── Routes ────────────────────────────────────────────────────────────

@router.post("/demo-login", summary="Login demo (locale/testing)")
async def demo_login(req: DemoLoginRequest):
    """
    Exchange demo credentials for a JWT token.
    Works without Supabase — for local development and product demos.
    """
    user = DEMO_USERS.get(req.email.lower().strip())
    if not user or user["password"] != req.password:
        raise HTTPException(status_code=401, detail="Credenziali non valide")

    token = _create_demo_token(user, req.email)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": DEMO_EXPIRY_H * 3600,
        "user": {
            "email": req.email,
            "name": user["name"],
            "role": user["role"],
            "hotel_id": user["hotel_id"],
        },
    }


@router.get("/me", summary="Profilo utente corrente")
async def get_me(user: Optional[UserProfile] = Depends(get_current_user)):
    """Valida il token e restituisce il profilo utente."""
    if not user:
        return {
            "authenticated": False,
            "auth_mode": "none",
            "message": "Nessun token fornito — modalità demo pubblica attiva",
            "demo_accounts": list(DEMO_USERS.keys()),
        }
    return {"authenticated": True, **user.model_dump()}


@router.get("/status", summary="Stato sistema autenticazione")
async def auth_status():
    """Restituisce la configurazione auth attiva (demo vs Supabase)."""
    supabase_live = bool(SUPABASE_URL and SUPABASE_KEY)
    return {
        "supabase_connected": supabase_live,
        "auth_mode": "supabase" if supabase_live else "demo",
        "demo_accounts_available": list(DEMO_USERS.keys()),
        "platform": "BAD360.ai v4.1",
    }
