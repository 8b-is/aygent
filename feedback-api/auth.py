#!/usr/bin/env python3
"""
Authentication and Rate Limiting for Feedback API
"""

import hashlib
import hmac
import time
import secrets
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from functools import wraps
from collections import defaultdict
import jwt
from fastapi import HTTPException, Header, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
import redis
import json
import os

# Configuration
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_urlsafe(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Agent API keys (in production, store in database)
AGENT_KEYS = {
    "agent_claude_001": {
        "secret": os.getenv("AGENT_CLAUDE_KEY", "sk_claude_" + secrets.token_urlsafe(32)),
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
        "secret": os.getenv("AGENT_OPENROUTER_KEY", "sk_or_" + secrets.token_urlsafe(32)),
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
except:
    redis_client = None  # Fallback to in-memory if Redis not available

# In-memory rate limiter fallback
rate_limit_cache = defaultdict(lambda: {"count": 0, "reset_time": time.time() + 60})


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


def verify_agent_key(agent_id: str, api_key: str) -> Optional[Dict[str, Any]]:
    """Verify agent API key"""
    if agent_id not in AGENT_KEYS:
        return None
    
    agent = AGENT_KEYS[agent_id]
    
    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(agent["secret"], api_key):
        return None
    
    return agent


def create_access_token(agent_id: str, agent_data: Dict[str, Any]) -> str:
    """Create JWT access token"""
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    
    payload = {
        "sub": agent_id,
        "name": agent_data["name"],
        "permissions": agent_data["permissions"],
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """Verify JWT token"""
    token = credentials.credentials
    
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def check_permission(required_permission: str):
    """Check if user has required permission"""
    def permission_checker(token_data: Dict = Depends(verify_token)):
        permissions = token_data.get("permissions", [])
        
        # Check for wildcard permission
        if "*" in permissions:
            return token_data
        
        # Check specific permission
        if required_permission not in permissions:
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied. Required: {required_permission}"
            )
        
        return token_data
    
    return permission_checker


class RateLimiter:
    """Rate limiting implementation"""
    
    @staticmethod
    def check_rate_limit(
        identifier: str,
        max_requests: int = 60,
        window_seconds: int = 60
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
                    "reset_time": current_time + window_seconds
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
    def get_remaining(identifier: str, max_requests: int = 60, window_seconds: int = 60) -> Dict[str, int]:
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
                "limit": max_requests
            }
        else:
            current_time = time.time()
            
            if identifier not in rate_limit_cache:
                return {
                    "remaining": max_requests,
                    "reset_in": window_seconds,
                    "limit": max_requests
                }
            
            limiter = rate_limit_cache[identifier]
            reset_in = max(0, int(limiter["reset_time"] - current_time))
            
            return {
                "remaining": max(0, max_requests - limiter["count"]),
                "reset_in": reset_in,
                "limit": max_requests
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
                identifier = f"api_key:{hashlib.sha256(api_key.encode()).hexdigest()[:16]}"
            
            # Check rate limit
            if not RateLimiter.check_rate_limit(identifier, max_requests, window_seconds):
                rate_info = RateLimiter.get_remaining(identifier, max_requests, window_seconds)
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Try again in {rate_info['reset_in']} seconds",
                    headers={
                        "X-RateLimit-Limit": str(rate_info["limit"]),
                        "X-RateLimit-Remaining": str(rate_info["remaining"]),
                        "X-RateLimit-Reset": str(rate_info["reset_in"]),
                    }
                )
            
            # Add rate limit headers to response
            response = await func(request, *args, **kwargs)
            rate_info = RateLimiter.get_remaining(identifier, max_requests, window_seconds)
            
            if hasattr(response, "headers"):
                response.headers["X-RateLimit-Limit"] = str(rate_info["limit"])
                response.headers["X-RateLimit-Remaining"] = str(rate_info["remaining"])
                response.headers["X-RateLimit-Reset"] = str(rate_info["reset_in"])
            
            return response
        
        return wrapper
    return decorator


def require_agent_auth(request: Request, x_api_key: Optional[str] = Header(None)) -> Dict[str, Any]:
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


# Admin authentication (simple for now, use proper auth in production)
ADMIN_USERS = {
    "admin": hashlib.sha256(os.getenv("ADMIN_PASSWORD", "change_me_please").encode()).hexdigest(),
    "hue": hashlib.sha256(os.getenv("HUE_PASSWORD", "quantum_waves_2025").encode()).hexdigest(),
}


def verify_admin(username: str, password: str) -> bool:
    """Verify admin credentials"""
    if username not in ADMIN_USERS:
        return False
    
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    return hmac.compare_digest(ADMIN_USERS[username], password_hash)


# Export functions for use in main API
__all__ = [
    "AgentAuth",
    "AdminLogin",
    "TokenResponse",
    "verify_agent_key",
    "create_access_token",
    "verify_token",
    "check_permission",
    "RateLimiter",
    "rate_limit",
    "require_agent_auth",
    "verify_admin",
    "AGENT_KEYS",
]