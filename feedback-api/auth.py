"""
Authentication and Rate Limiting for Feedback API
"""

import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from functools import wraps
from typing import Annotated, Any

import jwt
import redis
from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

# Configuration
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_urlsafe(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Agent API keys (in production, store in database)
AGENT_KEYS = {
    "agent_claude_001": {
        "secret": os.getenv(
            "AGENT_CLAUDE_KEY", "sk_claude_" + secrets.token_urlsafe(32)
        ),
        "name": "Claude MCP Agent",
        "permissions": ["feedback.submit", "feedback.read", "stats.read"],
        "rate_limit": 100,  # requests per minute
    },
    "agent_gpt_001": {
        "secret": os.getenv("AGENT_GPT_KEY", "sk_gpt_" + secrets.token_urlsafe(32)),
        "name": "GPT-4 Agent",
        "permissions": ["feedback.submit", "feedback.read", "stats.read"],
        "rate_limit": 100,
    },
    "agent_openrouter_001": {
        "secret": os.getenv(
            "AGENT_OPENROUTER_KEY", "sk_or_" + secrets.token_urlsafe(32)
        ),
        "name": "OpenRouter Assistant",
        "permissions": ["feedback.submit", "feedback.read", "stats.read", "llm.query"],
        "rate_limit": 50,
    },
    "admin_001": {
        "secret": os.getenv("ADMIN_API_KEY", "sk_admin_" + secrets.token_urlsafe(32)),
        "name": "Admin",
        "permissions": ["*"],  # All permissions
        "rate_limit": 1000,
    },
}

# Redis client for rate limiting
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
except (ValueError, redis.exceptions.RedisError):
    redis_client = None  # Fallback to in-memory if Redis not available

# In-memory rate limiter fallback
rate_limit_cache = defaultdict(lambda: {"count": 0, "reset_time": time.time() + 60})


async def verify_github_webhook(
    request: Request,
    x_hub_signature_256: Annotated[str | None, Header()] = None,
):
    """Authenticate the exact bytes GitHub signed before processing a delivery."""
    secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="GitHub webhook is not configured")
    if not x_hub_signature_256:
        raise HTTPException(status_code=403, detail="Invalid webhook signature")
    digest = hmac.new(
        secret.encode("utf-8"), await request.body(), hashlib.sha256
    ).hexdigest()
    expected = ("sha256=" + digest).encode("ascii")
    if not hmac.compare_digest(expected, x_hub_signature_256.encode("utf-8")):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")


class AgentAuth(BaseModel):
    """Agent authentication credentials"""

    agent_id: str
    api_key: str


class AdminLogin(BaseModel):
    """Admin login credentials"""

    username: str
    password: str


class TokenResponse(BaseModel):
    """JWT token response"""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = JWT_EXPIRATION_HOURS * 3600
    agent_name: str
    permissions: list


security = HTTPBearer()


def verify_agent_key(agent_id: str, api_key: str) -> dict[str, Any] | None:
    """Verify agent API key"""
    if agent_id not in AGENT_KEYS:
        return None

    agent = AGENT_KEYS[agent_id]

    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(agent["secret"], api_key):
        return None

    return agent


def create_access_token(agent_id: str, agent_data: dict[str, Any]) -> str:
    """Create JWT access token"""
    expire = datetime.now(UTC) + timedelta(hours=JWT_EXPIRATION_HOURS)

    payload = {
        "sub": agent_id,
        "name": agent_data["name"],
        "permissions": agent_data["permissions"],
        "exp": expire,
        "iat": datetime.now(UTC),
    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> dict[str, Any]:
    """Verify JWT token"""
    token = credentials.credentials

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def check_permission(required_permission: str):
    """Check if user has required permission"""

    def permission_checker(token_data: Annotated[dict, Depends(verify_token)]):
        permissions = token_data.get("permissions", [])

        # Check for wildcard permission
        if "*" in permissions:
            return token_data

        # Check specific permission
        if required_permission not in permissions:
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied. Required: {required_permission}",
            )

        return token_data

    return permission_checker


class RateLimiter:
    """Rate limiting implementation"""

    @staticmethod
    def check_rate_limit(
        identifier: str, max_requests: int = 60, window_seconds: int = 60
    ) -> bool:
        """Check if request is within rate limit"""

        if redis_client:
            # Use Redis for distributed rate limiting
            key = f"rate_limit:{identifier}"
            current_time = time.time()
            window_start = current_time - window_seconds

            # Remove old entries
            redis_client.zremrangebyscore(key, 0, window_start)

            # Count requests in current window
            request_count = redis_client.zcard(key)

            if request_count >= max_requests:
                return False

            # Add current request
            redis_client.zadd(key, {str(current_time): current_time})
            redis_client.expire(key, window_seconds)

            return True
        else:
            # Fallback to in-memory rate limiting
            current_time = time.time()

            if identifier not in rate_limit_cache:
                rate_limit_cache[identifier] = {
                    "count": 0,
                    "reset_time": current_time + window_seconds,
                }

            limiter = rate_limit_cache[identifier]

            # Reset if window has passed
            if current_time >= limiter["reset_time"]:
                limiter["count"] = 0
                limiter["reset_time"] = current_time + window_seconds

            if limiter["count"] >= max_requests:
                return False

            limiter["count"] += 1
            return True

    @staticmethod
    def get_remaining(
        identifier: str, max_requests: int = 60, window_seconds: int = 60
    ) -> dict[str, int]:
        """Get remaining requests and reset time"""

        if redis_client:
            key = f"rate_limit:{identifier}"
            current_time = time.time()
            window_start = current_time - window_seconds

            # Remove old entries
            redis_client.zremrangebyscore(key, 0, window_start)

            # Count requests in current window
            request_count = redis_client.zcard(key)

            return {
                "remaining": max(0, max_requests - request_count),
                "reset_in": window_seconds,
                "limit": max_requests,
            }
        else:
            current_time = time.time()

            if identifier not in rate_limit_cache:
                return {
                    "remaining": max_requests,
                    "reset_in": window_seconds,
                    "limit": max_requests,
                }

            limiter = rate_limit_cache[identifier]
            reset_in = max(0, int(limiter["reset_time"] - current_time))

            return {
                "remaining": max(0, max_requests - limiter["count"]),
                "reset_in": reset_in,
                "limit": max_requests,
            }


def rate_limit(max_requests: int = 60, window_seconds: int = 60):
    """Rate limiting decorator"""

    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            # Get identifier from IP or API key
            identifier = request.client.host

            # Check for API key in headers
            api_key = request.headers.get("X-API-Key")
            if api_key:
                # Use API key for rate limiting if present
                identifier = (
                    f"api_key:{hashlib.sha256(api_key.encode()).hexdigest()[:16]}"
                )

            # Check rate limit
            if not RateLimiter.check_rate_limit(
                identifier, max_requests, window_seconds
            ):
                rate_info = RateLimiter.get_remaining(
                    identifier, max_requests, window_seconds
                )
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Try again in {rate_info['reset_in']} seconds",
                    headers={
                        "X-RateLimit-Limit": str(rate_info["limit"]),
                        "X-RateLimit-Remaining": str(rate_info["remaining"]),
                        "X-RateLimit-Reset": str(rate_info["reset_in"]),
                    },
                )

            # Add rate limit headers to response
            response = await func(request, *args, **kwargs)
            rate_info = RateLimiter.get_remaining(
                identifier, max_requests, window_seconds
            )

            if hasattr(response, "headers"):
                response.headers["X-RateLimit-Limit"] = str(rate_info["limit"])
                response.headers["X-RateLimit-Remaining"] = str(rate_info["remaining"])
                response.headers["X-RateLimit-Reset"] = str(rate_info["reset_in"])

            return response

        return wrapper

    return decorator


def require_agent_auth(
    request: Request, x_api_key: str | None = Header(None)
) -> dict[str, Any]:
    """Require agent authentication via API key"""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")

    # Extract agent ID from API key format: "agent_id:api_key"
    if ":" not in x_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key format")

    agent_id, api_key = x_api_key.split(":", 1)

    agent = verify_agent_key(agent_id, api_key)
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Check rate limit for this agent
    if not RateLimiter.check_rate_limit(f"agent:{agent_id}", agent["rate_limit"], 60):
        raise HTTPException(status_code=429, detail="Agent rate limit exceeded")

    return {"agent_id": agent_id, **agent}


def load_admin_users() -> dict[str, str]:
    """Only explicitly configured, nonempty admin passwords enable login."""
    users = {}
    for username, variable in (("admin", "ADMIN_PASSWORD"), ("hue", "HUE_PASSWORD")):
        password = os.getenv(variable)
        if password:
            users[username] = hashlib.sha256(password.encode()).hexdigest()
    return users


ADMIN_USERS = load_admin_users()


def verify_admin(username: str, password: str) -> bool:
    """Verify admin credentials"""
    if username not in ADMIN_USERS:
        return False

    password_hash = hashlib.sha256(password.encode()).hexdigest()
    return hmac.compare_digest(ADMIN_USERS[username], password_hash)


# Export functions for use in main API
__all__ = [
    "AGENT_KEYS",
    "AdminLogin",
    "AgentAuth",
    "RateLimiter",
    "TokenResponse",
    "check_permission",
    "create_access_token",
    "rate_limit",
    "require_agent_auth",
    "verify_admin",
    "verify_agent_key",
    "verify_token",
]
