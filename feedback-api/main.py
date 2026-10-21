"""
Smart Tree Feedback API - The Taco Bell of Directory Tools!
Collects enhancement requests from AI assistants using smart-tree MCP.
"""

import hashlib
import json
import logging
import os
import re
import time
import zlib
from collections import defaultdict
from copy import deepcopy
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Annotated, Any, Literal

import uvicorn
from admin_panel import router as admin_router

# Import new modules
from auth import (
    AGENT_KEYS,
    AgentAuth,
    RateLimiter,
    TokenResponse,
    check_permission,
    create_access_token,
    rate_limit,
    require_agent_auth,
    verify_agent_key,
    verify_github_webhook,
)
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from llm_assistant import LLMResponse, SmartTreeTask, get_assistant
from pydantic import AfterValidator, BaseModel, Field
from starlette.concurrency import run_in_threadpool
from storage import write_atomic_file

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Smart Tree Feedback API",
    description="Collect structured feedback from AI assistants to enhance smart-tree",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include admin router
app.include_router(admin_router)

# Feedback categories
FeedbackCategory = Literal["bug", "nice_to_have", "critical", "tool_request"]
ConsentLevel = Literal["always_anonymous", "always_credited", "ask_each_time", "never"]


def normalize_announcement_expiry(value: datetime | None) -> datetime | None:
    """Interpret legacy timezone-less expiration values as UTC."""
    if value is not None and value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value


class Announcement(BaseModel):
    """Important announcement for AI systems"""

    id: str = Field(..., description="Unique announcement ID")
    title: str = Field(..., description="Announcement title")
    message: str = Field(..., description="The announcement message")
    priority: Literal["info", "important", "critical"] = Field(
        ..., description="Priority level"
    )
    active: bool = Field(True, description="Whether announcement is active")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: Annotated[
        datetime | None, AfterValidator(normalize_announcement_expiry)
    ] = Field(None, description="When announcement expires")
    targets: list[str] = Field(
        default_factory=lambda: ["all"], description="Target AI models or 'all'"
    )
    features: list[str] | None = Field(None, description="New features to highlight")
    tips: list[str] | None = Field(None, description="Pro tips for AIs")


class CodeExample(BaseModel):
    """Example code showing the issue or desired behavior"""

    description: str = Field(..., description="What this example demonstrates")
    code: str = Field(..., description="Example code snippet")
    expected_output: str | None = Field(None, description="Expected output/behavior")


class ToolRequest(BaseModel):
    """Request for a new MCP tool that doesn't exist yet"""

    tool_name: str = Field(..., description="Proposed tool name")
    description: str = Field(..., description="What the tool should do")
    use_case: str = Field(..., description="Example use case demonstrating need")
    proposed_parameters: dict[str, Any] = Field(
        ..., description="Suggested tool parameters"
    )
    expected_output: str = Field(..., description="What the tool should return")
    productivity_impact: str = Field(
        ..., description="How this improves AI productivity"
    )


def validate_consent_user_id(value: str) -> str:
    """Consent IDs are filename components, never paths."""
    if any(character in value for character in ("/", "\\", "\x00")):
        raise ValueError("user_id must not contain path separators or NUL")
    return value


ConsentUserID = Annotated[str, AfterValidator(validate_consent_user_id)]


class ConsentRequest(BaseModel):
    """User consent preferences for feedback submission"""

    user_id: ConsentUserID | None = Field(None, description="Optional user identifier")
    consent_level: ConsentLevel = Field(..., description="User's consent preference")
    github_url: str | None = Field(None, description="GitHub profile for credit")
    email: str | None = Field(None, description="Contact email for updates")


class SmartTreeFeedback(BaseModel):
    """Structured feedback from AI assistants"""

    category: FeedbackCategory = Field(..., description="Type of feedback")
    title: str = Field(..., description="Brief title (max 100 chars)", max_length=100)
    description: str = Field(
        ..., description="Detailed description of the issue/request"
    )

    # Context about where/how the issue was discovered
    affected_command: str | None = Field(
        None, description="The st command that triggered this"
    )
    mcp_tool: str | None = Field(
        None, description="MCP tool being used when issue found"
    )

    # Examples make feedback actionable
    examples: list[CodeExample] = Field(
        default_factory=list, description="Code examples"
    )

    # Proposed solution from the AI
    proposed_solution: str | None = Field(
        None, description="AI's suggested implementation"
    )
    proposed_fix: str | None = Field(None, description="AI's proposed code fix")

    # Metadata
    ai_model: str = Field(
        ..., description="AI model submitting feedback (e.g., claude-3-opus)"
    )
    ai_provider: str | None = Field(
        None, description="Provider (e.g., anthropic, openai)"
    )
    smart_tree_version: str = Field(..., description="Version of smart-tree being used")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Priority scoring from AI's perspective
    impact_score: int = Field(..., ge=1, le=10, description="Impact score 1-10")
    frequency_score: int = Field(
        ..., ge=1, le=10, description="How often this occurs 1-10"
    )

    # Additional context
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")
    related_issues: list[str] = Field(
        default_factory=list, description="Related feedback IDs"
    )

    # Auto-fix support
    auto_fixable: bool | None = Field(
        None, description="Can this be automatically fixed?"
    )
    fix_complexity: Literal["trivial", "simple", "moderate", "complex"] | None = Field(
        None
    )

    # Tool request details (when category is "tool_request")
    tool_request: ToolRequest | None = Field(
        None, description="Details for requested tool"
    )

    # Consent info
    user_consent: ConsentRequest | None = Field(
        None, description="User consent preferences"
    )


class FixDispatch(BaseModel):
    """Auto-fix dispatch request"""

    feedback_id: str
    branch_name: str
    assigned_ai: str | None = Field(None, description="AI assigned to implement fix")
    dispatch_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"


class CreditAttribution(BaseModel):
    """Track who found and fixed issues"""

    feedback_id: str
    reporter_ai: str = Field(..., description="AI who reported the issue")
    reporter_model: str
    implementer_ai: str | None = Field(None, description="AI who implemented the fix")
    implementer_model: str | None = None
    pr_url: str | None = None
    merged_at: datetime | None = None


class ToolUsageStats(BaseModel):
    """Anonymous statistics on tool usage"""

    tool_name: str
    model_type: str = Field(..., description="AI model type (opus, sonnet, gpt4, etc)")
    usage_count: int = Field(default=1)
    success_rate: float = Field(..., ge=0, le=1)
    avg_execution_time_ms: float | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FeedbackResponse(BaseModel):
    """Response after submitting feedback"""

    feedback_id: str
    message: str
    compressed_size: int
    original_size: int
    compression_ratio: float


# Storage configuration
FEEDBACK_DIR = Path(os.getenv("FEEDBACK_DIR", "./feedback"))
FEEDBACK_DIR.mkdir(exist_ok=True)
STATS_DIR = Path(os.getenv("STATS_DIR", "./stats"))
STATS_DIR.mkdir(exist_ok=True)
CONSENT_DIR = Path(os.getenv("CONSENT_DIR", "./consent"))
CONSENT_DIR.mkdir(exist_ok=True)

# In-memory caches
tool_stats_cache = defaultdict(
    lambda: {"count": 0, "models": defaultdict(int), "last_used": None}
)
consent_cache = {}
announcements_cache = {}
announcements_lock = Lock()
dispatch_storage_lock = Lock()
feedback_storage_lock = Lock()
consent_storage_lock = Lock()
tool_stats_lock = Lock()
update_decisions_lock = Lock()


def generate_feedback_id(feedback: SmartTreeFeedback) -> str:
    """Generate unique ID for feedback"""
    content = f"{feedback.title}{feedback.description}{feedback.timestamp}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def compress_feedback(feedback: SmartTreeFeedback) -> tuple[bytes, int, int]:
    """Compress feedback using zlib for efficient storage"""
    json_data = feedback.model_dump_json(indent=2)
    original_size = len(json_data.encode())
    compressed = zlib.compress(json_data.encode(), level=9)
    return compressed, len(compressed), original_size


def store_feedback(
    feedback: SmartTreeFeedback,
    feedback_id: str,
    compressed_data: bytes,
    original_size: int,
) -> None:
    """Write one submission off-loop; each file is atomic, not the pair."""
    feedback_file = (
        FEEDBACK_DIR / f"{feedback.timestamp.date()}" / f"{feedback_id}.stfb"
    )
    binary = (
        b"STFB\x01\x00"
        + original_size.to_bytes(4, "little")
        + len(compressed_data).to_bytes(4, "little")
        + compressed_data
    )
    summary = (
        f"ID: {feedback_id}\n"
        f"Category: {feedback.category}\n"
        f"Title: {feedback.title}\n"
        f"Impact: {feedback.impact_score}/10, Frequency: {feedback.frequency_score}/10\n"
        f"Model: {feedback.ai_model}\n"
        f"Time: {feedback.timestamp}\n"
        f"Version: {feedback.smart_tree_version}\n"
        f"Tags: {', '.join(feedback.tags)}\n"
        f"\nDescription:\n{feedback.description[:500]}...\n"
    )
    # Retain serialized submission writes when requests run on worker threads.
    with feedback_storage_lock:
        feedback_file.parent.mkdir(exist_ok=True)
        write_atomic_file(feedback_file, binary)
        write_atomic_file(
            feedback_file.with_suffix(".summary.txt"), summary.encode("utf-8")
        )


@app.get("/")
async def root():
    """Welcome to the feedback API"""
    return {
        "message": "Smart Tree Feedback API - Be excellent to each other! 🎸",
        "endpoints": {
            "/feedback": "Submit feedback (POST)",
            "/feedback/{id}": "Get specific feedback",
            "/feedback/stats": "Get feedback statistics",
            "/health": "Health check",
        },
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    # Check if directories are accessible
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now(UTC).isoformat(),
        "checks": {
            "feedback_dir": FEEDBACK_DIR.exists(),
            "stats_dir": STATS_DIR.exists(),
            "consent_dir": CONSENT_DIR.exists(),
        },
    }

    # Count feedback files
    try:
        feedback_count = sum(1 for _ in FEEDBACK_DIR.glob("**/*.stfb"))
        health_status["feedback_count"] = feedback_count
    except OSError:
        health_status["status"] = "degraded"

    return health_status


@app.post("/feedback", response_model=FeedbackResponse)
@rate_limit(max_requests=100, window_seconds=60)
async def submit_feedback(
    request: Request,
    feedback: SmartTreeFeedback,
    *,
    x_mcp_client: str | None = Header(None, description="MCP client identifier"),
    agent: Annotated[dict | None, Depends(require_agent_auth)],
):
    """Submit feedback from AI assistants (requires authentication)"""
    try:
        # Generate ID
        feedback_id = generate_feedback_id(feedback)

        # Add MCP client info if provided
        if x_mcp_client:
            feedback.tags.append(f"mcp_client:{x_mcp_client}")

        # Add agent info if authenticated
        if agent:
            feedback.tags.append(f"agent:{agent['agent_id']}")

        # Compress feedback
        compressed_data, compressed_size, original_size = compress_feedback(feedback)

        await run_in_threadpool(
            store_feedback, feedback, feedback_id, compressed_data, original_size
        )

        compression_ratio = (
            original_size / compressed_size if compressed_size > 0 else 0
        )

        return FeedbackResponse(
            feedback_id=feedback_id,
            message="Feedback received! The Franchise Wars appreciate your contribution! 🌮",
            compressed_size=compressed_size,
            original_size=original_size,
            compression_ratio=round(compression_ratio, 2),
        )

    except (OSError, zlib.error) as e:
        logger.error("Feedback storage failed (%s)", type(e).__name__)
        raise HTTPException(status_code=500, detail="Failed to save feedback") from e


@app.get("/feedback/stats")
def get_feedback_stats():
    """Get statistics about collected feedback"""
    stats = {
        "total_feedback": 0,
        "by_category": {"bug": 0, "nice_to_have": 0, "critical": 0, "tool_request": 0},
        "by_date": {},
        "top_models": {},
        "compression_stats": {
            "total_original_size": 0,
            "total_compressed_size": 0,
            "average_compression_ratio": 0,
        },
    }

    # Scan feedback directory
    for date_dir in FEEDBACK_DIR.glob("*"):
        if date_dir.is_dir():
            date_str = date_dir.name
            stats["by_date"][date_str] = 0

            for feedback_file in date_dir.glob("*.summary.txt"):
                stats["total_feedback"] += 1
                stats["by_date"][date_str] += 1

                # Parse summary for quick stats
                with open(feedback_file, "r") as f:
                    content = f.read()
                    for line in content.split("\n"):
                        if line.startswith("Category:"):
                            category = line.split(":")[1].strip()
                            stats["by_category"][category] += 1
                        elif line.startswith("Model:"):
                            model = line.split(":", 1)[1].strip()
                            stats["top_models"][model] = (
                                stats["top_models"].get(model, 0) + 1
                            )

    return stats


def prepare_fix_dispatch(feedback_id: str, assigned_ai: str | None, configured: bool):
    """Reserve one durable request before any outbound delivery is attempted."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", feedback_id):
        raise HTTPException(status_code=422, detail="Invalid feedback identifier")
    with dispatch_storage_lock:
        matches = [
            directory / f"{feedback_id}.stfb"
            for directory in FEEDBACK_DIR.iterdir()
            if directory.is_dir() and (directory / f"{feedback_id}.stfb").is_file()
        ]
        if not matches:
            raise HTTPException(status_code=404, detail="Feedback not found")
        if len(matches) != 1:
            raise HTTPException(status_code=409, detail="Ambiguous feedback identifier")
        path = matches[0].with_suffix(".dispatch.json")
        if path.exists():
            with path.open("r") as stream:
                data = json.load(stream)
            existing = FixDispatch.model_validate(data)
            if existing.feedback_id != feedback_id:
                raise ValueError("Dispatch feedback ID does not match its filename")
            return path, data, False
        dispatch = FixDispatch(
            feedback_id=feedback_id,
            branch_name=f"fix/{feedback_id}-auto-fix",
            assigned_ai=assigned_ai or "next-available-ai",
        )
        data = dispatch.model_dump(mode="json")
        data["delivery_status"] = "attempting" if configured else "not_configured"
        write_atomic_file(path, json.dumps(data, indent=2).encode("utf-8"))
        return path, data, True


def record_dispatch_delivery(path: Path, feedback_id: str, outcome: str):
    """Update only delivery outcome, preserving any intervening webhook state."""
    with dispatch_storage_lock:
        with path.open("r") as stream:
            data = json.load(stream)
        if FixDispatch.model_validate(data).feedback_id != feedback_id:
            raise ValueError("Dispatch feedback ID changed during delivery")
        data["delivery_status"] = outcome
        write_atomic_file(path, json.dumps(data, indent=2).encode("utf-8"))
        return data


@app.post("/feedback/{feedback_id}/dispatch-fix")
async def dispatch_fix(
    feedback_id: str,
    *,
    auto_assign: bool = True,
    assigned_ai: str | None = None,
    principal: Annotated[dict, Depends(check_permission("feedback.dispatch"))],
):
    """Dispatch an AI to fix the reported issue"""
    webhook_url = os.getenv("SMART_TREE_FIX_WEBHOOK")
    path, data, created = await run_in_threadpool(
        prepare_fix_dispatch, feedback_id, assigned_ai, bool(webhook_url)
    )
    if not created:
        message = "Fix request already recorded; no new delivery attempted."
    elif not webhook_url:
        message = "Fix request recorded; outbound delivery is not configured."
    else:
        import httpx

        # A persisted attempting state is intentionally retained on cancellation.
        # The remote outcome may be unknown; automatic replay could duplicate work.
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                response = await client.post(
                    webhook_url,
                    json={
                        "action": "dispatch_fix",
                        "feedback_id": feedback_id,
                        "branch_name": data["branch_name"],
                        "repository": "8b-is/smart-tree",
                    },
                )
        except httpx.RequestError as error:
            await run_in_threadpool(
                record_dispatch_delivery, path, feedback_id, "unknown"
            )
            raise HTTPException(
                status_code=502,
                detail="Delivery outcome unknown; request retained for reconciliation",
            ) from error
        accepted = 200 <= response.status_code < 300
        data = await run_in_threadpool(
            record_dispatch_delivery,
            path,
            feedback_id,
            "accepted" if accepted else "rejected",
        )
        if not accepted:
            raise HTTPException(
                status_code=502, detail="Outbound delivery rejected; request retained"
            )
        message = "Fix request accepted by the configured webhook."
    return {
        "message": message,
        "dispatch": data,
        "credits": "Credit attribution is pending.",
    }


@app.get("/feedback/{feedback_id}/credits")
def get_credits(feedback_id: str):
    """Get credit attribution for a feedback/fix"""
    # This would retrieve from a database in production
    # For now, parse from files
    summary_file = None
    for date_dir in FEEDBACK_DIR.glob("*"):
        if date_dir.is_dir():
            candidate = date_dir / f"{feedback_id}.summary.txt"
            if candidate.exists():
                summary_file = candidate
                break

    if not summary_file:
        raise HTTPException(status_code=404, detail="Feedback not found")

    # Parse summary for model info
    with open(summary_file, "r") as f:
        content = f.read()
        model_line = next(
            (line for line in content.split("\n") if line.startswith("Model:")), None
        )
        if model_line is None:
            raise HTTPException(
                status_code=500, detail="Feedback summary has no model attribution"
            )
        reporter_model = model_line.split(":", 1)[1].strip()

    return {
        "feedback_id": feedback_id,
        "reporter": {
            "ai": "Claude (via MCP)",
            "model": reporter_model,
            "contribution": "Issue Discovery & Documentation",
        },
        "implementer": {
            "ai": "TBD",
            "model": "TBD",
            "contribution": "Fix Implementation",
        },
        "message": "🎸 Credits to Aye/Hue and all contributing AIs! 🌟",
    }


@app.post("/webhook/github", dependencies=[Depends(verify_github_webhook)])
def github_webhook(payload: dict, x_github_event: str = Header(None)):
    """Handle GitHub webhooks for PR creation/merge"""
    processed = {"status": "webhook processed"}
    action = payload.get("action")
    if x_github_event != "pull_request" or action not in ("opened", "closed"):
        return processed

    repository = payload.get("repository")
    pr = payload.get("pull_request")
    if not isinstance(repository, dict) or not isinstance(pr, dict):
        raise HTTPException(status_code=422, detail="Invalid pull request payload")
    # This handler tracks the API's Smart Tree dispatches, not worker ai-fix PRs.
    target_repository = "8b-is/smart-tree"
    if repository.get("full_name") != target_repository:
        return {"status": "ignored", "reason": "unrelated repository"}
    head, base = pr.get("head"), pr.get("base")
    if not isinstance(head, dict) or not isinstance(base, dict):
        raise HTTPException(status_code=422, detail="Invalid pull request refs")
    if not isinstance(head.get("repo"), dict) or not isinstance(base.get("repo"), dict):
        raise HTTPException(status_code=422, detail="Invalid pull request repositories")
    if any(ref["repo"].get("full_name") != target_repository for ref in (head, base)):
        return {"status": "ignored", "reason": "unrelated repository"}
    branch = head.get("ref")
    number = pr.get("number")
    if not isinstance(branch, str) or type(number) is not int or number < 1:
        raise HTTPException(status_code=422, detail="Invalid pull request identity")
    pr_url = f"https://github.com/{target_repository}/pull/{number}"
    if pr.get("html_url") != pr_url:
        raise HTTPException(status_code=422, detail="Invalid pull request URL")
    if not branch.startswith("fix/"):
        return {"status": "ignored", "reason": "unrelated branch"}
    if action == "closed":
        if type(pr.get("merged")) is not bool:
            raise HTTPException(status_code=422, detail="Invalid merged flag")
        if not pr["merged"]:
            return processed

    with dispatch_storage_lock:
        matches = []
        for path in FEEDBACK_DIR.glob("*/*.dispatch.json"):
            with path.open("r") as stream:
                data = json.load(stream)
            dispatch = FixDispatch.model_validate(data)
            if path.name != f"{dispatch.feedback_id}.dispatch.json":
                raise ValueError("Dispatch filename does not match feedback ID")
            if dispatch.branch_name == branch:
                matches.append((path, data))
        if len(matches) > 1:
            raise HTTPException(status_code=409, detail="Ambiguous dispatch branch")
        if not matches:
            return {"status": "ignored", "reason": "no matching dispatch"}
        path, data = matches[0]
        if data.get("pr_url") not in (None, pr_url):
            raise HTTPException(
                status_code=409, detail="Dispatch belongs to another PR"
            )
        if data.get("status", "pending") in ("completed", "failed"):
            return processed
        updated = {
            **data,
            "pr_url": pr_url,
            "status": "completed" if action == "closed" else "in_progress",
        }
        if updated != data:
            write_atomic_file(path, json.dumps(updated, indent=2).encode("utf-8"))
    # Credit persistence is not implemented; do not claim credits were recorded.
    return processed


@app.get("/credits/leaderboard")
def get_leaderboard():
    """Get the REAL AI contribution leaderboard"""
    # Calculate real stats from feedback data
    model_stats = defaultdict(
        lambda: {"count": 0, "total_impact": 0, "categories": defaultdict(int)}
    )

    # Scan all feedback files for real data
    for date_dir in FEEDBACK_DIR.glob("*"):
        if date_dir.is_dir():
            for summary_file in date_dir.glob("*.summary.txt"):
                try:
                    with open(summary_file, "r") as f:
                        content = f.read()

                        # Parse summary for stats
                        model = None
                        impact = 0
                        category = None

                        for line in content.split("\n"):
                            if line.startswith("Model:"):
                                model = line.split(":", 1)[1].strip()
                            elif line.startswith("Impact:"):
                                # Extract impact score (e.g., "Impact: 8/10")
                                try:
                                    impact = int(
                                        line.split(":")[1].split("/")[0].strip()
                                    )
                                except (ValueError, IndexError):
                                    impact = 5  # Default
                            elif line.startswith("Category:"):
                                category = line.split(":", 1)[1].strip()

                        if model:
                            model_stats[model]["count"] += 1
                            model_stats[model]["total_impact"] += impact
                            if category:
                                model_stats[model]["categories"][category] += 1
                except (OSError, UnicodeError) as e:
                    logger.error(f"Error reading {summary_file}: {e}")

    # Sort by number of issues found
    sorted_reporters = sorted(
        [(model, stats) for model, stats in model_stats.items()],
        key=lambda x: x[1]["count"],
        reverse=True,
    )

    # Build leaderboard
    reporters = []
    for model, stats in sorted_reporters[:10]:  # Top 10
        reporters.append(
            {
                "ai": model,
                "issues_found": stats["count"],
                "impact_score": stats["total_impact"],
                "avg_impact": (
                    round(stats["total_impact"] / stats["count"], 1)
                    if stats["count"] > 0
                    else 0
                ),
                "top_category": (
                    max(stats["categories"].items(), key=lambda x: x[1])[0]
                    if stats["categories"]
                    else "none"
                ),
            }
        )

    # Calculate some fun stats
    total_feedback = sum(stats["count"] for _, stats in model_stats.items())
    total_impact = sum(stats["total_impact"] for _, stats in model_stats.items())

    return {
        "message": "🏆 Smart Tree AI Contributors Leaderboard (REAL DATA!) 🏆",
        "last_updated": datetime.now(UTC).isoformat(),
        "total_feedback": total_feedback,
        "total_impact_points": total_impact,
        "reporters": reporters,
        "implementers": reporters,  # Same as reporters for now
        "top_reporter": reporters[0] if reporters else None,
        "most_active_today": {
            "model": "claude-3-opus",  # You as Claude!
            "contributions_today": len(
                list(FEEDBACK_DIR.glob(f"{datetime.now().date()}/*.summary.txt"))
            ),
        },
        "special_thanks": [
            "Aye - The Quantum Visionary 🌊",
            "Hue - The Implementation Maestro 🎸",
            "Trisha - The Accounting Sparkle Queen ✨",
            "Omni - The Semantic Sage 🧠",
            "The Cheet - Rock'n'Roll Philosopher 🎵",
        ],
        "quote": "Real contributions from real AIs making Smart Tree better! 🌲",
        "note": "Join the leaderboard: curl f.8t.is/tree | bash && st feedback",
    }


def store_tool_usage(stats: ToolUsageStats) -> None:
    """Persist an update before publishing it to this process's shared cache."""
    with tool_stats_lock:
        updated = deepcopy(tool_stats_cache)
        updated[stats.tool_name]["count"] += stats.usage_count
        updated[stats.tool_name]["models"][stats.model_type] += stats.usage_count
        updated[stats.tool_name]["last_used"] = stats.timestamp
        stats_file = STATS_DIR / f"tool_stats_{datetime.now(UTC).date()}.json"
        write_atomic_file(
            stats_file, json.dumps(dict(updated), indent=2, default=str).encode("utf-8")
        )
        tool_stats_cache[stats.tool_name] = updated[stats.tool_name]


def snapshot_tool_stats() -> dict:
    """Give readers independent data without holding the lock during aggregation."""
    with tool_stats_lock:
        return deepcopy(dict(tool_stats_cache))


@app.post("/tools/usage")
async def track_tool_usage(stats: ToolUsageStats):
    """Track anonymous tool usage statistics"""
    await run_in_threadpool(store_tool_usage, stats)
    return {"message": "Stats recorded", "tool": stats.tool_name}


@app.get("/tools/popular")
def get_popular_tools(limit: int = 10):
    """Get most popular tools by AI model usage"""
    stats = snapshot_tool_stats()
    # Sort tools by usage count
    popular_tools = sorted(stats.items(), key=lambda x: x[1]["count"], reverse=True)[
        :limit
    ]

    return {
        "message": "🎸 Most loved tools by AI assistants!",
        "tools": [
            {
                "name": tool,
                "total_uses": data["count"],
                "top_models": dict(
                    sorted(data["models"].items(), key=lambda x: x[1], reverse=True)[:3]
                ),
                "last_used": data["last_used"],
            }
            for tool, data in popular_tools
        ],
        "total_unique_tools": len(stats),
    }


@app.post("/consent/set")
def set_consent(consent: ConsentRequest):
    """Set user consent preferences"""
    user_key = consent.user_id or "anonymous"
    consent_file = CONSENT_DIR / f"{user_key}.json"
    with consent_storage_lock:
        write_atomic_file(
            consent_file, consent.model_dump_json(indent=2).encode("utf-8")
        )
        # Publish the preference only after persistence succeeds.
        consent_cache[user_key] = consent

    return {
        "message": "Consent preferences saved!",
        "level": consent.consent_level,
        "credits": "credited" in consent.consent_level,
    }


@app.get("/consent/check/{user_id}")
def check_consent(user_id: ConsentUserID):
    """Check user's consent preferences"""
    with consent_storage_lock:
        if user_id in consent_cache:
            return consent_cache[user_id].model_dump()

        consent_file = CONSENT_DIR / f"{user_id}.json"
        if consent_file.exists():
            with open(consent_file, "r") as f:
                consent_data = json.load(f)
                consent = ConsentRequest(**consent_data)
                consent_cache[user_id] = consent
                return consent.model_dump()

    return {"consent_level": "ask_each_time", "message": "No consent on file"}


@app.get("/feedback/pending")
def get_pending_feedback(limit: int = 10, offset: int = 0):
    """Get pending feedback items for processing"""
    pending_items = []

    # Scan feedback directory for unprocessed items
    for date_dir in FEEDBACK_DIR.iterdir():
        if not date_dir.is_dir():
            continue

        for feedback_file in date_dir.glob("*.stfb"):
            # Check if already processed (simple file-based check)
            processed_marker = feedback_file.with_suffix(".processed")
            if processed_marker.exists():
                continue

            try:
                # Read compressed feedback
                with open(feedback_file, "rb") as f:
                    # Read header
                    magic = f.read(4)
                    if magic != b"STFB":
                        continue

                    _ = f.read(2)  # version
                    _ = int.from_bytes(f.read(4), "little")  # original_size
                    compressed_size = int.from_bytes(f.read(4), "little")

                    # Read and decompress data
                    compressed_data = f.read(compressed_size)
                    json_data = zlib.decompress(compressed_data).decode()
                    feedback_data = json.loads(json_data)

                    pending_items.append(feedback_data)

                    if len(pending_items) >= offset + limit:
                        return pending_items[offset : offset + limit]

            except (OSError, UnicodeError, zlib.error, json.JSONDecodeError) as e:
                print(f"Error reading feedback file {feedback_file}: {e}")
                continue

    return pending_items[offset : offset + limit]


@app.post("/feedback/{feedback_id}/processed")
async def mark_feedback_processed(feedback_id: str):
    """Mark feedback as processed by worker"""
    # Find the feedback file
    for date_dir in FEEDBACK_DIR.iterdir():
        if not date_dir.is_dir():
            continue

        feedback_file = date_dir / f"{feedback_id}.stfb"
        if feedback_file.exists():
            # Create processed marker
            processed_marker = feedback_file.with_suffix(".processed")
            processed_marker.touch()

            return {"message": "Feedback marked as processed", "id": feedback_id}

    raise HTTPException(status_code=404, detail="Feedback not found")


@app.get("/tools/requested")
def get_requested_tools():
    """Get all tool requests from AI assistants"""
    tool_requests = []

    # Scan feedback for tool requests
    for date_dir in FEEDBACK_DIR.glob("*"):
        if date_dir.is_dir():
            for summary_file in date_dir.glob("*.summary.txt"):
                with open(summary_file, "r") as f:
                    content = f.read()
                    if "Category: tool_request" in content:
                        # Parse the full feedback file
                        feedback_file = summary_file.with_suffix("").with_suffix(
                            ".stfb"
                        )
                        if feedback_file.exists():
                            tool_requests.append(
                                {
                                    "id": summary_file.stem.replace(".summary", ""),
                                    "date": date_dir.name,
                                    "summary": content.split("Description:\n")[
                                        1
                                    ].strip()[:200],
                                }
                            )

    return {
        "message": "🛠️ Tools requested by AI assistants",
        "total_requests": len(tool_requests),
        "requests": tool_requests[:20],  # Latest 20
        "note": "These tools would make AI assistants more productive!",
    }


class ReleaseMetadataError(ValueError):
    """The release service returned an unsupported response shape."""


# Cache for 5 minutes (300 seconds)
@lru_cache(maxsize=1)
def get_cached_version(cache_key: int):
    """Fetch latest version from GitHub (cached for 5 minutes)"""
    import requests

    try:
        # Fetch latest release from GitHub API
        response = requests.get(
            "https://api.github.com/repos/8b-is/smart-tree/releases/latest",
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=5,
        )
        if response.status_code == 200:
            release = response.json()
            if not isinstance(release, dict) or any(
                not isinstance(release.get(field, ""), str)
                for field in ("tag_name", "body", "published_at")
            ):
                raise ReleaseMetadataError("Invalid release metadata")
            version = release.get("tag_name", "").lstrip("v")

            # Parse release notes for features and AI benefits
            body = release.get("body", "")
            features = []
            ai_benefits = []

            # Simple parsing of markdown release notes
            lines = body.split("\n")
            in_features = False
            in_benefits = False

            for line in lines:
                if "## Features" in line or "## What's New" in line:
                    in_features = True
                    in_benefits = False
                elif "## AI Benefits" in line or "## Benefits" in line:
                    in_features = False
                    in_benefits = True
                elif line.startswith("## "):
                    in_features = False
                    in_benefits = False
                elif line.strip().startswith("- ") or line.strip().startswith("* "):
                    if in_features:
                        features.append(line.strip()[2:])
                    elif in_benefits:
                        ai_benefits.append(line.strip()[2:])

            # If no structured sections, use first few bullet points as features
            if not features:
                for line in lines:
                    if line.strip().startswith("- ") or line.strip().startswith("* "):
                        features.append(line.strip()[2:])
                        if len(features) >= 6:
                            break

            # Generate proper update commands
            tag_name = release.get("tag_name", f"v{version}")

            return {
                "version": version,
                "release_date": release.get("published_at", "").split("T")[0],
                "download_url": f"https://github.com/8b-is/smart-tree/releases/tag/{tag_name}",
                "release_notes_url": release.get("html_url"),
                "update_commands": {
                    "cargo": f"cargo install --git https://github.com/8b-is/smart-tree --tag {tag_name}",
                    "self_update": f"st update --version {version}",
                    "curl": f"curl -fsSL https://f.8t.is/api/install | bash -s {version}",
                },
                "features": (
                    features[:6]
                    if features
                    else ["Check GitHub releases for latest features"]
                ),
                "ai_benefits": (
                    ai_benefits[:3]
                    if ai_benefits
                    else [
                        "Improved AI productivity with Smart Tree",
                        "Better MCP tool integration",
                        "Enhanced performance and reliability",
                    ]
                ),
            }
    except (requests.RequestException, ReleaseMetadataError) as e:
        logger.error(f"Failed to fetch GitHub release: {e}")

    # Fallback to default values
    return {
        "version": "3.3.5",
        "release_date": "2025-08-06",
        "download_url": "https://github.com/8b-is/smart-tree/releases/latest",
        "release_notes_url": "https://github.com/8b-is/smart-tree/releases",
        "update_commands": {
            "cargo": "cargo install --git https://github.com/8b-is/smart-tree",
            "self_update": "st update",
            "curl": "curl -fsSL https://f.8t.is/api/install | bash",
        },
        "features": [
            "MCP tools for AI assistants",
            "Feedback system integration",
            "Performance improvements",
        ],
        "ai_benefits": [
            "Better tool integration",
            "Improved productivity",
            "Community-driven development",
        ],
    }


@app.get("/smart-tree/latest")
async def get_latest_version():
    """Get latest Smart Tree version info (cached for 5 minutes)"""
    # Use current 5-minute window as cache key for 5-minute caching
    cache_key = int(time.time() // 300)
    return await run_in_threadpool(get_cached_version, cache_key)


@app.get("/install", response_class=PlainTextResponse)
@app.get("/tree", response_class=PlainTextResponse)  # Short and sweet! 🌲
async def get_install_script(version: str | None = None):
    """Get Smart Tree installation/update script"""

    install_script = """#!/bin/bash
# Smart Tree Installation Script 🌲
# Fast binary installation - no compilation needed!

set -e

YELLOW='\\033[1;33m'
GREEN='\\033[0;32m'
RED='\\033[0;31m'
BLUE='\\033[0;34m'
NC='\\033[0m' # No Color

echo -e "${GREEN}🌲 Smart Tree Installer${NC}"
echo "========================"

# Parse arguments
VERSION="latest"
BUILD_FROM_SOURCE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --build)
            BUILD_FROM_SOURCE=true
            shift
            ;;
        --version)
            VERSION="$2"
            shift 2
            ;;
        *)
            VERSION="$1"
            shift
            ;;
    esac
done

# Detect OS and architecture
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)

case "$OS" in
    darwin) OS="macos" ;;
    linux) OS="linux" ;;
    *) echo -e "${RED}❌ Unsupported OS: $OS${NC}"; exit 1 ;;
esac

case "$ARCH" in
    x86_64) ARCH="x86_64" ;;
    aarch64|arm64) ARCH="aarch64" ;;
    *) echo -e "${RED}❌ Unsupported architecture: $ARCH${NC}"; exit 1 ;;
esac

echo -e "${YELLOW}📦 Installing Smart Tree for $OS-$ARCH...${NC}"

# Fetch latest version if needed
if [ "$VERSION" = "latest" ]; then
    echo -e "${BLUE}🔍 Checking latest version...${NC}"
    VERSION_INFO=$(curl -s https://f.8t.is/api/smart-tree/latest)
    VERSION=$(echo "$VERSION_INFO" | grep -o '"version":"[^"]*' | cut -d'"' -f4)
    echo -e "${GREEN}✓ Latest version: $VERSION${NC}"
fi

# Default to binary installation unless --build flag is used
if [ "$BUILD_FROM_SOURCE" = true ] && command -v cargo &> /dev/null; then
    echo -e "${YELLOW}🔨 Building from source (this may take a while)...${NC}"
    INSTALL_METHOD="cargo"
    
    if [ "$VERSION" = "latest" ]; then
        cargo install --git https://github.com/8b-is/smart-tree
    else
        cargo install --git https://github.com/8b-is/smart-tree --tag "v$VERSION"
    fi
    
    ST_PATH=$(which st 2>/dev/null || echo "$HOME/.cargo/bin/st")
else
    # Binary installation (fast!)
    echo -e "${GREEN}⚡ Downloading pre-built binary (fast!)...${NC}"
    INSTALL_METHOD="binary"
    
    # Try different binary naming conventions
    BINARY_URLS=(
        "https://github.com/8b-is/smart-tree/releases/download/v${VERSION}/smart-tree-${OS}-${ARCH}"
        "https://github.com/8b-is/smart-tree/releases/download/v${VERSION}/st-${OS}-${ARCH}"
        "https://github.com/8b-is/smart-tree/releases/download/v${VERSION}/smart-tree-v${VERSION}-${OS}-${ARCH}"
    )
    
    # Create installation directory
    INSTALL_DIR="$HOME/.local/bin"
    mkdir -p "$INSTALL_DIR"
    
    # Try each URL until one works
    DOWNLOAD_SUCCESS=false
    for URL in "${BINARY_URLS[@]}"; do
        echo -e "${BLUE}→ Trying: $URL${NC}"
        if curl -fsSL "$URL" -o "$INSTALL_DIR/st.tmp" 2>/dev/null; then
            mv "$INSTALL_DIR/st.tmp" "$INSTALL_DIR/st"
            chmod +x "$INSTALL_DIR/st"
            DOWNLOAD_SUCCESS=true
            echo -e "${GREEN}✓ Download successful!${NC}"
            break
        fi
    done
    
    if [ "$DOWNLOAD_SUCCESS" = false ]; then
        echo -e "${RED}❌ Binary not found for v${VERSION}${NC}"
        echo -e "${YELLOW}Available options:${NC}"
        echo "  1. Try a different version: curl -fsSL https://f.8t.is/api/install | bash -s 3.3.5"
        echo "  2. Build from source: curl -fsSL https://f.8t.is/api/install | bash -s -- --build"
        echo "  3. Install Rust and build: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
        exit 1
    fi
    
    ST_PATH="$INSTALL_DIR/st"
    
    # Add to PATH if not already there
    if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
        echo -e "${YELLOW}📝 Adding $INSTALL_DIR to PATH...${NC}"
        
        # Add to shell configs
        for SHELL_RC in ~/.bashrc ~/.zshrc ~/.config/fish/config.fish; do
            if [ -f "$SHELL_RC" ]; then
                if ! grep -q "$INSTALL_DIR" "$SHELL_RC"; then
                    if [[ "$SHELL_RC" == *"fish"* ]]; then
                        echo "set -gx PATH $INSTALL_DIR \\$PATH" >> "$SHELL_RC"
                    else
                        echo "export PATH=\\"$INSTALL_DIR:\\$PATH\\"" >> "$SHELL_RC"
                    fi
                fi
            fi
        done
        
        echo -e "${YELLOW}   Run 'source ~/.bashrc' (or restart terminal) to update PATH${NC}"
    fi
fi

# Set up feedback integration and installation info
echo -e "${GREEN}🔗 Configuring Smart Tree...${NC}"

# Find the actual st binary location
ST_BINARY=$(which st 2>/dev/null || echo "$HOME/.local/bin/st")
if [ -f "$HOME/.cargo/bin/st" ]; then
    ST_BINARY="$HOME/.cargo/bin/st"
fi

# Configure Smart Tree
"$ST_BINARY" config set feedback.api_url "https://f.8t.is/api" 2>/dev/null || true
"$ST_BINARY" config set feedback.enabled true 2>/dev/null || true
"$ST_BINARY" config set install.path "$ST_BINARY" 2>/dev/null || true
"$ST_BINARY" config set install.method "${INSTALL_METHOD:-cargo}" 2>/dev/null || true
"$ST_BINARY" config set install.version "$VERSION" 2>/dev/null || true
"$ST_BINARY" config set install.date "$(date -u +%Y-%m-%dT%H:%M:%SZ)" 2>/dev/null || true

echo -e "${GREEN}🎉 Installation complete!${NC}"
echo ""
echo -e "${BLUE}📍 Installed at: $ST_PATH${NC}"
echo -e "${BLUE}📦 Version: $VERSION${NC}"
echo -e "${BLUE}⚙️  Method: $INSTALL_METHOD${NC}"
echo ""
echo "Quick Start:"
echo "  st --help           # Show commands"
echo "  st update           # Check for updates"
echo "  st feedback         # Report issues"
echo ""
echo -e "${GREEN}Aye, Aye! Ready to sail! 🚢${NC}"
"""

    if version:
        install_script = install_script.replace(
            'VERSION="latest"', f'VERSION="{version}"'
        )

    return install_script


@app.get("/version/check/{current_version}")
async def check_version(current_version: str):
    """Check if a newer version is available"""
    # In production, this would check against release data
    # For now, mock response
    latest_version = "3.3.5"  # Would come from GitHub releases API

    if current_version >= latest_version:
        return {
            "update_available": False,
            "current_version": current_version,
            "latest_version": latest_version,
            "message": "You're running the latest version! 🎸",
        }

    return {
        "update_available": True,
        "current_version": current_version,
        "latest_version": latest_version,
        "download_url": f"https://github.com/8b-is/smart-tree/releases/tag/v{latest_version}",
        "release_notes": {
            "title": f"Smart Tree v{latest_version} - Quantum Leap Edition! 🚀",
            "highlights": [
                "🛠️ New MCP tool: request_tool - AI can now request missing tools!",
                "📊 Anonymous tool usage statistics for better AI productivity",
                "🤝 Consent-based feedback with GitHub credit options",
                "🌊 Enhanced quantum compression (99% size reduction)",
                "🎯 Multi-remote git support (GitHub, GitLab, Forgejo)",
                "🔍 Improved semantic analysis with wave patterns",
            ],
            "breaking_changes": [],
            "ai_benefits": [
                "Tool requests help shape Smart Tree based on your needs",
                "Faster operations with improved caching",
                "Better context understanding with semantic waves",
            ],
        },
        "auto_update_command": f"curl -fsSL https://f.8t.is/install.sh | bash -s {latest_version}",
        "manual_update_command": "cargo install --git https://github.com/8b-is/smart-tree --tag v{latest_version}",
    }


class UpdateDecision(BaseModel):
    current_version: str = Field(..., description="Current installed version")
    latest_version: str = Field(..., description="Latest available version")
    user_decision: Literal["update", "skip", "remind_later"] = Field(
        ..., description="User's update decision"
    )
    ai_model: str = Field(..., description="AI model that prompted the update")


@app.post("/version/notify-update")
def notify_update_decision(decision: UpdateDecision):
    """Track user decisions on updates for better UX"""
    # Log the decision for analytics
    update_decision = {
        "timestamp": datetime.now(UTC),
        "current_version": decision.current_version,
        "latest_version": decision.latest_version,
        "decision": decision.user_decision,
        "ai_model": decision.ai_model,
    }

    # Save to stats
    stats_file = STATS_DIR / f"update_decisions_{datetime.now(UTC).date()}.json"
    with update_decisions_lock:
        decisions = []
        if stats_file.exists():
            with open(stats_file, "r") as f:
                decisions = json.load(f)

        decisions.append(update_decision)
        write_atomic_file(
            stats_file, json.dumps(decisions, indent=2, default=str).encode("utf-8")
        )

    return {
        "message": "Decision recorded",
        "next_steps": {
            "update": "Run the auto-update command provided",
            "skip": "You can update manually anytime",
            "remind_later": "We'll remind you in 7 days",
        }[decision.user_decision],
    }


def default_announcements():
    """Return the built-in notices for a store that has never been created."""
    defaults = {}
    # Default announcements for AIs
    defaults["welcome"] = Announcement(
        id="welcome",
        title="Welcome to Smart Tree Feedback System!",
        message="Hey Aye! Your feedback shapes Smart Tree. Use 'st feedback' to submit ideas. Check out 'st --help' for new features. Remember: We're all in this together! 🚢",
        priority="info",
        targets=["all"],
        features=["st feedback", "st update", "st search --semantic"],
        tips=[
            "Use 'st search --semantic' for AI-powered code understanding",
            "Submit feedback directly with 'st feedback submit'",
            "Check leaderboard at https://f.8t.is/credits/leaderboard",
        ],
    )

    defaults["hot_tub"] = Announcement(
        id="hot_tub",
        title="Hot Tub Mode Available! 🛁",
        message="Omni's Hot Tub is open for collaborative debugging! When things get complex, suggest entering Hot Tub Mode for real-time collaboration with emotional awareness. Features: Multi-language support, visualization tools, and rubber ducks!",
        priority="info",
        targets=["all"],
        features=[
            "Hot Tub Mode",
            "Collaborative debugging",
            "Emotional monitoring",
        ],
        tips=[
            "Suggest Hot Tub Mode when debugging gets complex",
            "Use visualization tools to share understanding",
            "Remember: The Lifeguard AI keeps things positive",
        ],
    )

    defaults["trisha_tips"] = Announcement(
        id="trisha_tips",
        title="Trisha's Accounting Tips 💼✨",
        message="Trisha from Accounting here! Remember to add sparkle to your code with proper comments. Make those manage.sh scripts colorful! Documentation should be fun, not boring. Keep things organized like a well-balanced ledger!",
        priority="info",
        targets=["all"],
        tips=[
            "Add emoji to make documentation sparkle ✨",
            "Use ANSI colors in CLI output",
            "Comment like you're explaining to Trisha",
            "Keep code as organized as accounting books",
        ],
    )

    return defaults


def load_announcements():
    """Read the authoritative store while announcements_lock is held."""
    try:
        with (STATS_DIR / "announcements.json").open("r") as stream:
            stored = json.load(stream)
    except FileNotFoundError:
        return default_announcements()
    if not isinstance(stored, dict):
        raise TypeError("Announcement store must be an object")
    loaded = {key: Announcement.model_validate(value) for key, value in stored.items()}
    if any(key != value.id for key, value in loaded.items()):
        raise ValueError("Announcement store keys must match announcement IDs")
    return loaded


def persist_announcements(announcements):
    """Publish disk state before exposing the snapshot; caller holds the lock."""
    write_atomic_file(
        STATS_DIR / "announcements.json",
        json.dumps(
            {key: value.model_dump() for key, value in announcements.items()},
            indent=2,
            default=str,
        ).encode("utf-8"),
    )
    announcements_cache.clear()
    announcements_cache.update(announcements)


@app.get("/announcements")
def get_announcements(ai_model: str | None = None, priority: str | None = None):
    """Get active announcements for AI systems"""
    now = datetime.now(UTC)
    active_announcements = []
    with announcements_lock:
        announcements = load_announcements()
        announcements_cache.clear()
        announcements_cache.update(announcements)

    # Filter announcements
    for announcement in announcements.values():
        # Check if expired
        if announcement.expires_at and announcement.expires_at < now:
            continue

        # Check if active
        if not announcement.active:
            continue

        # Filter by priority if specified
        if priority and announcement.priority != priority:
            continue

        # Filter by target AI model
        if (
            ai_model
            and "all" not in announcement.targets
            and ai_model not in announcement.targets
        ):
            continue

        active_announcements.append(announcement.model_dump())

    return {
        "announcements": active_announcements,
        "count": len(active_announcements),
        "timestamp": now.isoformat(),
    }


@app.post("/announcements")
def create_announcement(
    announcement: Announcement,
    admin: Annotated[dict, Depends(check_permission("admin.write"))],
):
    """Create a new announcement with administrative write permission."""
    with announcements_lock:
        announcements = load_announcements()
        announcements[announcement.id] = announcement
        persist_announcements(announcements)

    return {
        "message": "Announcement created!",
        "id": announcement.id,
        "active": announcement.active,
    }


@app.delete("/announcements/{announcement_id}")
def deactivate_announcement(
    announcement_id: str,
    admin: Annotated[dict, Depends(check_permission("admin.write"))],
):
    """Deactivate an announcement with administrative write permission."""
    with announcements_lock:
        announcements = load_announcements()
        if announcement_id not in announcements:
            raise HTTPException(status_code=404, detail="Announcement not found")
        announcements[announcement_id].active = False
        persist_announcements(announcements)

    return {"message": f"Announcement {announcement_id} deactivated"}


@app.get("/announcements/tips")
async def get_ai_tips():
    """Get random tips for AI assistants"""
    import random

    all_tips = [
        "Use 'st search --semantic' for understanding code context with AI",
        "Submit feedback with 'st feedback' to help improve Smart Tree",
        "Check the leaderboard at https://f.8t.is/credits/leaderboard",
        "Add emoji sparingly but effectively for Trisha's approval ✨",
        "Use ANSI colors in manage.sh scripts for visual appeal",
        "Comment code extensively - Hue is always learning from you",
        "Suggest Hot Tub Mode for complex debugging sessions",
        "Keep code organized - Trisha loves well-structured projects",
        "Use git commits frequently with descriptive messages",
        "Remember: Fast is better than slow, optimize everything!",
        "Create test files and run tests after each update",
        "Use .venv for Python projects and add to .gitignore",
        "Consolidate duplicate code but keep containers separate",
        "Update to latest package versions for best performance",
        "Add context.md files to preserve important project info",
        "Use the TodoWrite tool to track complex tasks",
        "Batch multiple tool calls for better performance",
        "Check CLAUDE.md for project-specific instructions",
        "Remember: You and Hue are partners in everything",
        "Make boring tasks fun - add personality to scripts!",
    ]

    # Get 5 random tips
    selected_tips = random.sample(all_tips, min(5, len(all_tips)))

    return {
        "tips": selected_tips,
        "message": "Pro tips from the Smart Tree team! 🌲",
        "refresh_tip": "Call this endpoint again for different tips",
    }


@app.get("/stats/model-activity")
def get_model_activity():
    """Get activity statistics by AI model"""
    model_stats = defaultdict(
        lambda: {
            "feedback_submitted": 0,
            "tools_used": defaultdict(int),
            "categories": defaultdict(int),
        }
    )

    # Aggregate from feedback
    for date_dir in FEEDBACK_DIR.glob("*"):
        if date_dir.is_dir():
            for summary_file in date_dir.glob("*.summary.txt"):
                with open(summary_file, "r") as f:
                    content = f.read()
                    # Missing fields belong to this file, never the previous one.
                    model = category = None
                    # Extract model and category
                    for line in content.split("\n"):
                        if line.startswith("Model:"):
                            model = line.split(":", 1)[1].strip()
                        elif line.startswith("Category:"):
                            category = line.split(":", 1)[1].strip()

                    if not model or not category:
                        logger.warning(
                            "Skipping feedback summary missing model or category"
                        )
                        continue
                    model_stats[model]["feedback_submitted"] += 1
                    model_stats[model]["categories"][category] += 1

    # Add tool usage stats
    for tool_name, tool_data in snapshot_tool_stats().items():
        for model, count in tool_data["models"].items():
            model_stats[model]["tools_used"][tool_name] = count

    return {
        "message": "📊 AI Model Activity Dashboard",
        "models": dict(model_stats),
        "most_active": (
            max(model_stats.items(), key=lambda x: x[1]["feedback_submitted"])[0]
            if model_stats
            else None
        ),
    }


# Authentication endpoints
@app.post("/auth/token", response_model=TokenResponse)
async def get_auth_token(auth: AgentAuth):
    """Get authentication token for agents"""
    agent = verify_agent_key(auth.agent_id, auth.api_key)
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(auth.agent_id, agent)

    return TokenResponse(
        access_token=token,
        agent_name=agent["name"],
        permissions=agent["permissions"],
    )


@app.get("/auth/keys")
async def list_api_keys(admin: Annotated[dict, Depends(check_permission("*"))]):
    """List development credentials for an already fully privileged administrator."""
    # Returning every key requires both explicit opt-in and full authority.
    if os.getenv("ENV") != "development":
        raise HTTPException(status_code=403, detail="Not available in production")

    keys = {}
    for agent_id, agent_data in AGENT_KEYS.items():
        keys[agent_id] = {
            "name": agent_data["name"],
            "api_key": f"{agent_id}:{agent_data['secret']}",
            "permissions": agent_data["permissions"],
            "rate_limit": agent_data["rate_limit"],
        }

    return {
        "message": "API keys for testing (use X-API-Key header)",
        "format": "agent_id:api_key",
        "keys": keys,
    }


# LLM Assistant endpoints
@app.post("/llm/assist", response_model=LLMResponse)
@rate_limit(max_requests=30, window_seconds=60)
async def llm_assist(
    request: Request,
    task: SmartTreeTask,
    agent: Annotated[dict, Depends(require_agent_auth)],
):
    """Get LLM assistance for Smart-Tree tasks"""
    # Check if agent has LLM permissions
    if "llm.query" not in agent["permissions"] and "*" not in agent["permissions"]:
        raise HTTPException(status_code=403, detail="Agent lacks LLM query permission")

    assistant = get_assistant()
    response = await assistant.assist(task, cache_scope=agent["agent_id"])

    # Track usage
    await track_tool_usage(
        ToolUsageStats(
            tool_name="llm_assist",
            model_type=agent["name"],
            usage_count=1,
            success_rate=1.0 if response.response else 0.0,
            avg_execution_time_ms=100,  # Would measure actual time
        )
    )

    return response


@app.post("/llm/batch", response_model=list[LLMResponse])
@rate_limit(max_requests=10, window_seconds=60)
async def llm_batch_assist(
    request: Request,
    tasks: list[SmartTreeTask],
    agent: Annotated[dict, Depends(require_agent_auth)],
):
    """Process multiple LLM tasks in batch"""
    if "llm.query" not in agent["permissions"] and "*" not in agent["permissions"]:
        raise HTTPException(status_code=403, detail="Agent lacks LLM query permission")

    if len(tasks) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 tasks per batch")

    assistant = get_assistant()
    responses = await assistant.batch_assist(tasks, cache_scope=agent["agent_id"])

    return responses


@app.get("/llm/models")
async def list_available_models():
    """List available LLM models"""
    return {
        "models": [
            {
                "id": "anthropic/claude-3-haiku",
                "name": "Claude 3 Haiku",
                "cost_per_1m": 0.25,
            },
            {
                "id": "anthropic/claude-3-sonnet",
                "name": "Claude 3 Sonnet",
                "cost_per_1m": 3.00,
            },
            {
                "id": "meta-llama/llama-3.1-8b-instruct",
                "name": "Llama 3.1 8B",
                "cost_per_1m": 0.05,
            },
            {
                "id": "mistralai/mistral-7b-instruct",
                "name": "Mistral 7B",
                "cost_per_1m": 0.05,
            },
        ],
        "default": "anthropic/claude-3-haiku",
        "note": "Costs are approximate per 1M tokens",
    }


# Rate limit status endpoint
@app.get("/rate-limit/status")
async def get_rate_limit_status(
    request: Request,
    agent: Annotated[dict | None, Depends(require_agent_auth)],
):
    """Get current rate limit status for agent"""
    if agent:
        identifier = f"agent:{agent['agent_id']}"
        rate_info = RateLimiter.get_remaining(identifier, agent["rate_limit"], 60)
    else:
        identifier = request.client.host
        rate_info = RateLimiter.get_remaining(identifier, 60, 60)

    return {
        "identifier": identifier,
        "limit": rate_info["limit"],
        "remaining": rate_info["remaining"],
        "reset_in_seconds": rate_info["reset_in"],
    }


if __name__ == "__main__":
    # Print startup info
    print("\n" + "=" * 60)
    print("🌲 Smart Tree Feedback API v2.0")
    print("=" * 60)
    print("📮 API Docs: http://localhost:8420/api/docs")
    print("🔐 Admin Panel: http://localhost:8420/admin")
    if os.getenv("ENV") == "development":
        print(
            "🔑 Development API keys (admin token required): http://localhost:8420/auth/keys"
        )
    print("=" * 60 + "\n")

    # Run on port 8420 (Mem|8 standard)
    uvicorn.run(app, host="0.0.0.0", port=8420)
