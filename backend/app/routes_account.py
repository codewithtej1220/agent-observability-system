"""Accounts, sign-in, workspaces, members, API keys, provider credentials."""
from __future__ import annotations

import logging
import secrets
from typing import Any, Dict, Literal, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from . import crypto
from .auth import (
    CSRF_HEADER, CSRF_VALUE, Ctx, create_session, demo_workspace, end_session, hash_password, login_throttle,
    new_api_key, require_user, role, sha256, validate_password, verify_password,
)
from .config import get_settings
from .db import get_db
from .orm import (
    DEFAULT_WORKSPACE_SETTINGS, PROVIDERS, ApiKey, Membership, ProviderCredential, User, UserSession, Workspace, utcnow,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
OAUTH_STATE_COOKIE = "aobs_oauth_state"


def _csrf(request: Request) -> None:
    if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise HTTPException(403, "Missing X-Requested-With header")


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _onboard(db: Session, user: User) -> int:
    """Give a new user a workspace. The first user adopts the unclaimed demo workspace."""
    demo = demo_workspace(db)
    if demo is not None and db.query(Membership).filter(Membership.workspace_id == demo.id).count() == 0:
        db.add(Membership(user_id=user.id, workspace_id=demo.id, role="admin"))
        db.commit()
        return demo.id
    first = (user.name or user.email.split("@")[0]).split(" ")[0]
    ws = Workspace(name=f"{first}'s workspace", settings=dict(DEFAULT_WORKSPACE_SETTINGS))
    db.add(ws)
    db.flush()
    db.add(Membership(user_id=user.id, workspace_id=ws.id, role="admin"))
    db.commit()
    return ws.id


def _me(db: Session, ctx: Ctx) -> Dict[str, Any]:
    rows = (db.query(Membership, Workspace).join(Workspace, Workspace.id == Membership.workspace_id)
            .filter(Membership.user_id == ctx.user.id).order_by(Workspace.name).all())
    return {
        "user": {"id": ctx.user.id, "email": ctx.user.email, "name": ctx.user.name,
                 "has_password": bool(ctx.user.password_hash), "google_linked": bool(ctx.user.google_sub)},
        "workspace": {"id": ctx.workspace.id, "name": ctx.workspace.name, "role": ctx.role},
        "workspaces": [{"id": w.id, "name": w.name, "role": m.role} for m, w in rows],
    }


# =========================================================================== auth
class SignupIn(BaseModel):
    email: EmailStr
    password: str
    name: str = Field("", max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


@router.get("/auth/config", tags=["auth"])
def auth_config():
    return {"google_enabled": get_settings().google_enabled}


@router.post("/auth/signup", tags=["auth"])
def signup(body: SignupIn, request: Request, response: Response, db: Session = Depends(get_db)):
    _csrf(request)
    email = _normalize_email(body.email)
    validate_password(body.password)
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")
    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    ws_id = _onboard(db, user)
    create_session(db, user, response, request, ws_id)
    return {"ok": True}


@router.post("/auth/login", tags=["auth"])
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    _csrf(request)
    email = _normalize_email(body.email)
    throttle_key = f"{email}|{request.client.host if request.client else ''}"
    login_throttle.check(throttle_key)
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(body.password, user.password_hash):
        login_throttle.fail(throttle_key)
        if user is not None and not user.password_hash and user.google_sub:
            raise HTTPException(401, "This account uses Google sign-in.")
        raise HTTPException(401, "Incorrect email or password")
    login_throttle.reset(throttle_key)
    create_session(db, user, response, request)
    return {"ok": True}


@router.post("/auth/logout", tags=["auth"])
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    _csrf(request)
    end_session(db, request, response)
    return {"ok": True}


@router.get("/auth/me", tags=["auth"])
def me(ctx: Ctx = Depends(require_user), db: Session = Depends(get_db)):
    return _me(db, ctx)


class SwitchIn(BaseModel):
    workspace_id: int


@router.post("/auth/switch-workspace", tags=["auth"])
def switch_workspace(body: SwitchIn, ctx: Ctx = Depends(require_user), db: Session = Depends(get_db)):
    m = db.query(Membership).filter(Membership.user_id == ctx.user.id,
                                    Membership.workspace_id == body.workspace_id).first()
    if m is None:
        raise HTTPException(404, "Workspace not found")
    ctx.session.workspace_id = body.workspace_id
    db.commit()
    return {"ok": True}


class PasswordIn(BaseModel):
    current_password: Optional[str] = None
    new_password: str


@router.post("/auth/password", tags=["auth"])
def change_password(body: PasswordIn, ctx: Ctx = Depends(require_user), db: Session = Depends(get_db)):
    user = ctx.user
    if user.password_hash and not verify_password(body.current_password or "", user.password_hash):
        raise HTTPException(401, "Current password is incorrect")
    validate_password(body.new_password)
    user.password_hash = hash_password(body.new_password)
    # Sign out every other session.
    db.query(UserSession).filter(UserSession.user_id == user.id,
                                 UserSession.token_hash != ctx.session.token_hash).delete()
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- Google
def _google_redirect_uri() -> str:
    return get_settings().public_url.rstrip("/") + "/api/auth/google/callback"


@router.get("/auth/google/login", tags=["auth"])
def google_login():
    s = get_settings()
    if not s.google_enabled:
        raise HTTPException(404, "Google sign-in is not configured")
    state = secrets.token_urlsafe(24)
    url = GOOGLE_AUTH_URL + "?" + urlencode({
        "client_id": s.google_client_id, "redirect_uri": _google_redirect_uri(), "response_type": "code",
        "scope": "openid email profile", "state": state, "prompt": "select_account",
    })
    resp = RedirectResponse(url, status_code=302)
    resp.set_cookie(OAUTH_STATE_COOKIE, state, max_age=600, httponly=True, secure=s.cookie_secure,
                    samesite="lax", path="/api/auth/google")
    return resp


async def google_exchange(code: str) -> Dict[str, Any]:
    """Exchange the authorization code and fetch the verified profile. Separate for testing."""
    s = get_settings()
    async with httpx.AsyncClient(timeout=15) as client:
        tok = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code, "client_id": s.google_client_id, "client_secret": s.google_client_secret,
            "redirect_uri": _google_redirect_uri(), "grant_type": "authorization_code",
        })
        tok.raise_for_status()
        info = await client.get(GOOGLE_USERINFO_URL,
                                headers={"Authorization": f"Bearer {tok.json()['access_token']}"})
        info.raise_for_status()
        return info.json()


@router.get("/auth/google/callback", tags=["auth"])
async def google_callback(request: Request, code: str = "", state: str = "", error: str = "",
                          db: Session = Depends(get_db)):
    s = get_settings()
    base = s.public_url.rstrip("/")

    def fail(msg: str):
        r = RedirectResponse(f"{base}/login?" + urlencode({"error": msg}), status_code=302)
        r.delete_cookie(OAUTH_STATE_COOKIE, path="/api/auth/google")
        return r

    if error:
        return fail("Google sign-in was cancelled")
    expected = request.cookies.get(OAUTH_STATE_COOKIE)
    if not expected or not state or not secrets.compare_digest(expected, state):
        return fail("Sign-in session expired, please try again")
    try:
        profile = await google_exchange(code)
    except Exception:  # noqa: BLE001
        log.exception("Google token exchange failed")
        return fail("Could not verify your Google account")
    if not profile.get("email") or not profile.get("email_verified"):
        return fail("Your Google account email is not verified")

    sub, email = profile["sub"], _normalize_email(profile["email"])
    user = db.query(User).filter(User.google_sub == sub).first()
    if user is None:
        user = db.query(User).filter(User.email == email).first()
        if user is not None:
            user.google_sub = sub  # link: Google verified ownership of this email
        else:
            user = User(email=email, name=profile.get("name", ""), google_sub=sub)
            db.add(user)
        db.commit()
        if db.query(Membership).filter(Membership.user_id == user.id).count() == 0:
            _onboard(db, user)
    resp = RedirectResponse(f"{base}/", status_code=302)
    create_session(db, user, resp, request)
    resp.delete_cookie(OAUTH_STATE_COOKIE, path="/api/auth/google")
    return resp


# =========================================================================== workspaces
class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


@router.post("/workspaces", tags=["workspace"])
def create_workspace(body: WorkspaceIn, ctx: Ctx = Depends(require_user), db: Session = Depends(get_db)):
    ws = Workspace(name=body.name.strip(), settings=dict(DEFAULT_WORKSPACE_SETTINGS))
    db.add(ws)
    db.flush()
    db.add(Membership(user_id=ctx.user.id, workspace_id=ws.id, role="admin"))
    ctx.session.workspace_id = ws.id
    db.commit()
    return {"id": ws.id, "name": ws.name}


class SettingsIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    store_content: Optional[bool] = None
    redact_pii: Optional[bool] = None
    retention_days: Optional[int] = Field(None, ge=1, le=3650)
    auto_judge: Optional[bool] = None
    judge_sample_rate: Optional[float] = Field(None, ge=0, le=1)
    judge_credential_id: Optional[int] = None
    judge_model: Optional[str] = Field(None, max_length=100)


@router.get("/workspace", tags=["workspace"])
def get_workspace(ctx: Ctx = Depends(require_user)):
    return {"id": ctx.workspace.id, "name": ctx.workspace.name, "role": ctx.role,
            "settings": {**DEFAULT_WORKSPACE_SETTINGS, **(ctx.workspace.settings or {})}}


@router.patch("/workspace", tags=["workspace"])
def update_workspace(body: SettingsIn, ctx: Ctx = Depends(role("admin")), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    if "name" in data:
        ctx.workspace.name = data.pop("name").strip()
    if data.get("judge_credential_id") is not None:
        cred = db.get(ProviderCredential, data["judge_credential_id"])
        if cred is None or cred.workspace_id != ctx.workspace_id:
            raise HTTPException(422, "Unknown provider credential")
    ctx.workspace.settings = {**DEFAULT_WORKSPACE_SETTINGS, **(ctx.workspace.settings or {}), **data}
    db.commit()
    return get_workspace(ctx)


# --------------------------------------------------------------------------- members
class MemberIn(BaseModel):
    email: EmailStr
    role: Literal["admin", "member", "viewer"] = "member"


class RoleIn(BaseModel):
    role: Literal["admin", "member", "viewer"]


@router.get("/workspace/members", tags=["workspace"])
def list_members(ctx: Ctx = Depends(require_user), db: Session = Depends(get_db)):
    rows = (db.query(Membership, User).join(User, User.id == Membership.user_id)
            .filter(Membership.workspace_id == ctx.workspace_id).order_by(User.email).all())
    return [{"user_id": u.id, "email": u.email, "name": u.name, "role": m.role,
             "joined_at": m.created_at.isoformat() + "Z", "last_login_at": u.last_login_at.isoformat() + "Z" if u.last_login_at else None}
            for m, u in rows]


@router.post("/workspace/members", tags=["workspace"])
def add_member(body: MemberIn, ctx: Ctx = Depends(role("admin")), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == _normalize_email(body.email)).first()
    if user is None:
        raise HTTPException(404, "No account with this email. Ask them to sign up first, then add them.")
    if db.query(Membership).filter(Membership.user_id == user.id, Membership.workspace_id == ctx.workspace_id).first():
        raise HTTPException(409, "Already a member")
    db.add(Membership(user_id=user.id, workspace_id=ctx.workspace_id, role=body.role))
    db.commit()
    return {"ok": True}


def _admins(db: Session, ws_id: int) -> int:
    return db.query(Membership).filter(Membership.workspace_id == ws_id, Membership.role == "admin").count()


@router.patch("/workspace/members/{user_id}", tags=["workspace"])
def change_role(user_id: int, body: RoleIn, ctx: Ctx = Depends(role("admin")), db: Session = Depends(get_db)):
    m = db.query(Membership).filter(Membership.user_id == user_id, Membership.workspace_id == ctx.workspace_id).first()
    if m is None:
        raise HTTPException(404, "Member not found")
    if m.role == "admin" and body.role != "admin" and _admins(db, ctx.workspace_id) == 1:
        raise HTTPException(409, "A workspace needs at least one admin")
    m.role = body.role
    db.commit()
    return {"ok": True}


@router.delete("/workspace/members/{user_id}", tags=["workspace"])
def remove_member(user_id: int, ctx: Ctx = Depends(role("admin")), db: Session = Depends(get_db)):
    m = db.query(Membership).filter(Membership.user_id == user_id, Membership.workspace_id == ctx.workspace_id).first()
    if m is None:
        raise HTTPException(404, "Member not found")
    if m.role == "admin" and _admins(db, ctx.workspace_id) == 1:
        raise HTTPException(409, "A workspace needs at least one admin")
    db.delete(m)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- API keys
class ApiKeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


def _key_out(k: ApiKey) -> Dict[str, Any]:
    return {"id": k.id, "name": k.name, "prefix": k.prefix, "created_at": k.created_at.isoformat() + "Z",
            "last_used_at": k.last_used_at.isoformat() + "Z" if k.last_used_at else None,
            "revoked": k.revoked_at is not None}


@router.get("/workspace/api-keys", tags=["workspace"])
def list_api_keys(ctx: Ctx = Depends(require_user), db: Session = Depends(get_db)):
    rows = db.query(ApiKey).filter(ApiKey.workspace_id == ctx.workspace_id).order_by(ApiKey.id.desc()).all()
    return [_key_out(k) for k in rows]


@router.post("/workspace/api-keys", tags=["workspace"])
def create_api_key(body: ApiKeyIn, ctx: Ctx = Depends(role("member")), db: Session = Depends(get_db)):
    if ctx.user is None:
        raise HTTPException(403, "API keys can only be created by signed-in users")
    key = new_api_key()
    row = ApiKey(workspace_id=ctx.workspace_id, name=body.name.strip(), prefix=key[:12],
                 key_hash=sha256(key), created_by=ctx.user.id)
    db.add(row)
    db.commit()
    return {**_key_out(row), "key": key, "note": "Copy this key now; it will not be shown again."}


@router.delete("/workspace/api-keys/{key_id}", tags=["workspace"])
def revoke_api_key(key_id: int, ctx: Ctx = Depends(role("member")), db: Session = Depends(get_db)):
    row = db.get(ApiKey, key_id)
    if row is None or row.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "API key not found")
    if ctx.role != "admin" and row.created_by != (ctx.user.id if ctx.user else None):
        raise HTTPException(403, "Only admins can revoke keys created by others")
    row.revoked_at = utcnow()
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- provider keys
class CredentialIn(BaseModel):
    provider: Literal["openai", "anthropic", "gemini"]
    api_key: str = Field(min_length=8, max_length=500)
    name: str = Field("default", min_length=1, max_length=100)
    is_default: bool = True


def _cred_out(c: ProviderCredential) -> Dict[str, Any]:
    return {"id": c.id, "provider": c.provider, "name": c.name, "key_hint": c.key_hint, "is_default": c.is_default,
            "created_at": c.created_at.isoformat() + "Z",
            "last_used_at": c.last_used_at.isoformat() + "Z" if c.last_used_at else None}


@router.get("/workspace/credentials", tags=["workspace"])
def list_credentials(ctx: Ctx = Depends(require_user), db: Session = Depends(get_db)):
    rows = (db.query(ProviderCredential).filter(ProviderCredential.workspace_id == ctx.workspace_id)
            .order_by(ProviderCredential.provider, ProviderCredential.name).all())
    return [_cred_out(c) for c in rows]


@router.post("/workspace/credentials", tags=["workspace"])
def add_credential(body: CredentialIn, ctx: Ctx = Depends(role("admin")), db: Session = Depends(get_db)):
    if body.provider not in PROVIDERS:
        raise HTTPException(422, "Unknown provider")
    secret = body.api_key.strip()
    existing = db.query(ProviderCredential).filter(
        ProviderCredential.workspace_id == ctx.workspace_id, ProviderCredential.provider == body.provider,
        ProviderCredential.name == body.name).first()
    if body.is_default:
        db.query(ProviderCredential).filter(ProviderCredential.workspace_id == ctx.workspace_id,
                                            ProviderCredential.provider == body.provider).update({"is_default": False})
    row = existing or ProviderCredential(workspace_id=ctx.workspace_id, provider=body.provider, name=body.name,
                                         created_by=ctx.user.id if ctx.user else None)
    row.encrypted_key = crypto.encrypt(secret)
    row.key_hint = crypto.hint(secret)
    row.is_default = body.is_default or not db.query(ProviderCredential).filter(
        ProviderCredential.workspace_id == ctx.workspace_id, ProviderCredential.provider == body.provider,
        ProviderCredential.is_default.is_(True)).count()
    db.add(row)
    db.commit()
    return _cred_out(row)


@router.delete("/workspace/credentials/{cred_id}", tags=["workspace"])
def delete_credential(cred_id: int, ctx: Ctx = Depends(role("admin")), db: Session = Depends(get_db)):
    row = db.get(ProviderCredential, cred_id)
    if row is None or row.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Credential not found")
    db.delete(row)
    db.commit()
    return {"ok": True}
