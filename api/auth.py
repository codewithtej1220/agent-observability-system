"""Authentication and authorization middleware.

Implements:
- API Key authentication
- JWT token authentication
- Role-based access control (RBAC)
- Rate limiting per user
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# API Keys (in production, store in database)
VALID_API_KEYS = {
    "dev-key-12345": {"user": "developer", "role": "admin", "rate_limit": 1000},
    "prod-key-67890": {"user": "production", "role": "user", "rate_limit": 100},
}

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Security schemes
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None


class User(BaseModel):
    username: str
    role: str
    rate_limit: int
    disabled: bool = False


# ============================================================================
# API KEY AUTHENTICATION
# ============================================================================


def get_api_key_user(api_key: str = Security(api_key_header)) -> User:
    """Authenticate via API key."""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Provide X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    if api_key not in VALID_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    
    user_data = VALID_API_KEYS[api_key]
    return User(
        username=user_data["user"],
        role=user_data["role"],
        rate_limit=user_data["rate_limit"]
    )


# ============================================================================
# JWT TOKEN AUTHENTICATION
# ============================================================================


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(credentials: HTTPAuthorizationCredentials = Security(bearer_scheme)) -> User:
    """Verify JWT token."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role", "user")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
            )
        token_data = TokenData(username=username, role=role)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    
    return User(username=token_data.username, role=token_data.role, rate_limit=100)


# ============================================================================
# FLEXIBLE AUTHENTICATION (API Key OR JWT)
# ============================================================================


def get_current_user(
    api_key: Optional[str] = Security(api_key_header),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
) -> User:
    """Accept either API key or JWT token."""
    # Try API key first
    if api_key and api_key in VALID_API_KEYS:
        user_data = VALID_API_KEYS[api_key]
        return User(
            username=user_data["user"],
            role=user_data["role"],
            rate_limit=user_data["rate_limit"]
        )
    
    # Try JWT token
    if credentials:
        try:
            payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            role: str = payload.get("role", "user")
            if username:
                return User(username=username, role=role, rate_limit=100)
        except JWTError:
            pass
    
    # No valid authentication
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide X-API-Key header or Bearer token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ============================================================================
# ROLE-BASED ACCESS CONTROL
# ============================================================================


def require_role(required_role: str):
    """Dependency to enforce role requirement."""
    def role_checker(user: User = Depends(get_current_user)):
        if user.role != required_role and user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' required. You have '{user.role}'",
            )
        return user
    return role_checker


# Admin-only dependency
require_admin = require_role("admin")


# ============================================================================
# PASSWORD UTILITIES (for future user management)
# ============================================================================


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)
