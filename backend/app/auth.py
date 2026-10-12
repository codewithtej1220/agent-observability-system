"""Authentication and authorization.

Two ways in, both resolving to a workspace:

* Dashboard users: email/password or Google sign-in -> server-side session.
  The browser holds a random token in an httpOnly, SameSite=Lax cookie; the
  database stores only its SHA-256, so sessions are revocable (logout) and a
  database leak does not leak live sessions. State-changing requests must
  also send `X-Requested-With: aobs` (a custom header a cross-site page cannot
  add without a CORS preflight), which blocks CSRF.

* Machines (SDK, LLM gateway): workspace API keys `aobs_...`, sent as
  `X-API-Key`, `Authorization: Bearer`, `x-api-key` (Anthropic SDK) or
  `x-goog-api-key` / `?key=` (Gemini SDK). Only the SHA-256 is stored.

Roles per workspace: admin (manage members, keys, settings), member (use and
configure monitoring), viewer (read-only).
"""
from __future__ import annotations

import hashlib
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import timedelta
from typing import Deque, Dict, Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .orm import ApiKey, Membership, User, UserSession, Workspace, utcnow

SESSION_COOKIE = "aobs_session"
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "aobs"
API_KEY_PREFIX = "aobs_"
DEMO_WORKSPACE_NAME = "Demo workspace"
ROLE_RANK = {"viewer": 0, "member": 1, "admin": 2}

_hasher = PasswordHasher()


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


# --------------------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: Optional[str]) -> bool:
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(422, "Password must be at least 8 characters")
    if len(password) > 256:
        raise HTTPException(422, "Password is too long")
    if password.isdigit() or password.isalpha():
        raise HTTPException(422, "Password must contain both letters and numbers or symbols")


class LoginThrottle:
    """At most `limit` failed attempts per key in `window` seconds (in-process)."""

    def __init__(self, limit: int = 10, window: int = 900):
        self.limit, self.window = limit, window
        self.fails: Dict[str, Deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        q = self.fails[key]
        now = time.monotonic()
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(429, "Too many failed sign-in attempts. Try again in a few minutes.")

    def fail(self, key: str) -> None:
        self.fails[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        self.fails.pop(key, None)


login_throttle = LoginThrottle()


# --------------------------------------------------------------------------- context
@dataclass
class Ctx:
    workspace: Workspace
    role: str
    user: Optional[User] = None
    api_key: Optional[ApiKey] = None
    session: Optional[UserSession] = None

    @property
    def workspace_id(self) -> int:
        return self.workspace.id

    def require(self, role: str) -> None:
        if ROLE_RANK[self.role] < ROLE_RANK[role]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires {role} role in this workspace")


# --------------------------------------------------------------------------- sessions
def create_session(db: Session, user: User, response: Response, request: Request,
                   workspace_id: Optional[int] = None) -> UserSession:
    s = get_settings()
    token = secrets.token_urlsafe(32)
    if workspace_id is None:
        m = db.query(Membership).filter(Membership.user_id == user.id).order_by(Membership.id).first()
        workspace_id = m.workspace_id if m else None
    sess = UserSession(token_hash=sha256(token), user_id=user.id, workspace_id=workspace_id,
                       expires_at=utcnow() + timedelta(days=s.session_days),
                       user_agent=(request.headers.get("user-agent") or "")[:300])
    user.last_login_at = utcnow()
    db.add(sess)
    db.commit()
    response.set_cookie(SESSION_COOKIE, token, max_age=s.session_days * 86400, httponly=True,
                        secure=s.cookie_secure, samesite="lax", path="/")
    return sess


def end_session(db: Session, request: Request, response: Response) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.query(UserSession).filter(UserSession.token_hash == sha256(token)).delete()
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


def _session_ctx(request: Request, db: Session) -> Optional[Ctx]:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    sess = db.get(UserSession, sha256(token))
    if sess is None or sess.expires_at < utcnow():
        return None
    user = db.get(User, sess.user_id)
    if user is None:
        return None
    m = None
    if sess.workspace_id is not None:
        m = db.query(Membership).filter(Membership.user_id == user.id,
                                        Membership.workspace_id == sess.workspace_id).first()
    if m is None:  # workspace removed or membership revoked: fall back to any membership
        m = db.query(Membership).filter(Membership.user_id == user.id).order_by(Membership.id).first()
        if m is None:
            return None
        sess.workspace_id = m.workspace_id
        db.commit()
    return Ctx(workspace=db.get(Workspace, m.workspace_id), role=m.role, user=user, session=sess)


# --------------------------------------------------------------------------- API keys
def new_api_key() -> str:
    return API_KEY_PREFIX + secrets.token_urlsafe(30)


def extract_api_key(request: Request) -> Optional[str]:
    h = request.headers
    auth = h.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (h.get("x-api-key") or h.get("x-goog-api-key") or request.query_params.get("key") or None)


def demo_workspace(db: Session) -> Optional[Workspace]:
    return db.query(Workspace).filter(Workspace.name == DEMO_WORKSPACE_NAME).order_by(Workspace.id).first()


def _api_key_ctx(key: str, db: Session) -> Optional[Ctx]:
    s = get_settings()
    if s.dev_key_enabled and secrets.compare_digest(key, s.dev_api_key):
        ws = demo_workspace(db)
        return Ctx(workspace=ws, role="member") if ws else None
    if not key.startswith(API_KEY_PREFIX):
        return None
    row = db.query(ApiKey).filter(ApiKey.key_hash == sha256(key), ApiKey.revoked_at.is_(None)).first()
    if row is None:
        return None
    now = utcnow()
    if row.last_used_at is None or (now - row.last_used_at).total_seconds() > 60:
        row.last_used_at = now  # throttled write
        db.commit()
    return Ctx(workspace=db.get(Workspace, row.workspace_id), role="member", api_key=row)


# --------------------------------------------------------------------------- dependencies
def require_access(request: Request, db: Session = Depends(get_db)) -> Ctx:
    """Session (dashboard) or API key (SDK). Rejects cross-site state changes."""
    ctx = _session_ctx(request, db)
    if ctx is not None:
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing X-Requested-With header")
        return ctx
    key = extract_api_key(request)
    if key:
        ctx = _api_key_ctx(key, db)
        if ctx is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked API key")
        return ctx
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in or provide an API key")


def require_user(ctx: Ctx = Depends(require_access)) -> Ctx:
    """Signed-in dashboard user only (not API keys)."""
    if ctx.user is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This endpoint requires a signed-in user")
    return ctx


def role(min_role: str):
    def dep(ctx: Ctx = Depends(require_access)) -> Ctx:
        ctx.require(min_role)
        return ctx
    return dep


def api_key_ctx_or_401(request: Request, db: Session) -> Ctx:
    """For the LLM gateway: API key only (SDK clients), errors in provider-agnostic JSON."""
    key = extract_api_key(request)
    ctx = _api_key_ctx(key, db) if key else None
    if ctx is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Use a workspace API key (aobs_...) as the SDK api_key when calling the gateway")
    return ctx
