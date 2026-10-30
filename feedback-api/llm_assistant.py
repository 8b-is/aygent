"""
OpenRouter LLM Integration for Smart-Tree Assistance
Helps with boring/repetitive tasks and provides context
"""

import asyncio
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from storage import write_atomic_file

# OpenRouter configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Cache directory for responses
CACHE_DIR = Path(os.getenv("LLM_CACHE_DIR", "./llm_cache"))
CACHE_DIR.mkdir(exist_ok=True)

# Model preferences for different tasks
MODEL_PREFERENCES = {
    "code_generation": "anthropic/claude-3-haiku",  # Fast and cheap for simple code
    "code_review": "anthropic/claude-3-sonnet",  # Better analysis
    "documentation": "meta-llama/llama-3.1-8b-instruct",  # Good for docs
    "refactoring": "anthropic/claude-3-haiku",  # Quick refactoring
    "testing": "mistralai/mistral-7b-instruct",  # Test generation
    "default": "anthropic/claude-3-haiku",  # Default fallback
}


class SmartTreeTask(BaseModel):
    """Task request for LLM assistance"""

    task_type: str = Field(
        ..., description="Type of task: code_generation, review, docs, etc"
    )
    context: str = Field(..., description="Current code context or file content")
    request: str = Field(..., description="What needs to be done")
    language: str | None = Field(None, description="Programming language")
    constraints: list[str] | None = Field(
        None, description="Any constraints or requirements"
    )
    examples: list[str] | None = Field(None, description="Example code or outputs")


class LLMResponse(BaseModel):
    """Response from LLM"""

    task_id: str
    model_used: str
    response: str
    tokens_used: int
    cost_estimate: float
    cached: bool = False
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SmartTreeAssistant:
    """OpenRouter-powered assistant for Smart-Tree tasks"""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or OPENROUTER_API_KEY
        if not self.api_key:
            raise ValueError("OpenRouter API key required")

        self.client = httpx.AsyncClient(
            base_url=OPENROUTER_BASE_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://8t.is",
                "X-Title": "Smart-Tree Assistant",
            },
            timeout=30.0,
        )

    def _get_cache_key(
        self, task: SmartTreeTask, cache_scope: str | None = None
    ) -> str:
        """Hash the complete task, model and trusted caller scope unambiguously."""
        content = json.dumps(
            {
                "version": 2,
                "scope": cache_scope,
                "model": self._select_model(task.task_type),
                "task": task.model_dump(mode="json"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        # Legacy truncated keys remain on disk but are never reused.
        return "v2-" + hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _get_cached_response(self, cache_key: str) -> LLMResponse | None:
        """Check a complete cached response that is less than one hour old."""
        cache_file = CACHE_DIR / f"{cache_key}.json"
        try:
            with cache_file.open("r") as stream:
                # Read the age of the opened file, even if another request replaces it.
                age = time.time() - os.fstat(stream.fileno()).st_mtime
                if 0 <= age < 3600:
                    response = LLMResponse(**json.load(stream))
                    response.cached = True
                    return response
        except FileNotFoundError:
            return None
        return None

    def _save_to_cache(self, cache_key: str, response: LLMResponse):
        """Publish a complete response without truncating the previous cache entry."""
        cache_file = CACHE_DIR / f"{cache_key}.json"
        write_atomic_file(
            cache_file,
            json.dumps(response.model_dump(), indent=2, default=str).encode("utf-8"),
        )

    def _select_model(self, task_type: str) -> str:
        """Select appropriate model for task"""
        return MODEL_PREFERENCES.get(task_type, MODEL_PREFERENCES["default"])

    def _build_prompt(self, task: SmartTreeTask) -> str:
        """Build optimized prompt for the task"""
        prompt_parts = []

        # Task-specific system prompts
        if task.task_type == "code_generation":
            prompt_parts.append(
                "You are a code generation assistant. Generate clean, efficient code "
                "following best practices. Be concise and avoid unnecessary comments."
            )
        elif task.task_type == "code_review":
            prompt_parts.append(
                "You are a code reviewer. Identify issues, suggest improvements, "
                "and highlight good practices. Focus on actionable feedback."
            )
        elif task.task_type == "documentation":
            prompt_parts.append(
                "You are a documentation writer. Create clear, concise documentation "
                "with examples where helpful. Use proper markdown formatting."
            )
        elif task.task_type == "refactoring":
            prompt_parts.append(
                "You are a refactoring assistant. Improve code structure, reduce duplication, "
                "and enhance readability while maintaining functionality."
            )
        elif task.task_type == "testing":
            prompt_parts.append(
                "You are a test generation assistant. Create comprehensive test cases "
                "covering edge cases and common scenarios."
            )
        else:
            prompt_parts.append(
                "You are Smart-Tree Assistant, helping with file tree and code tasks. "
                "Be concise and practical."
            )

        # Add context
        prompt_parts.append(f"\nContext:\n{task.context[:2000]}")  # Limit context size

        # Add the actual request
        prompt_parts.append(f"\nTask: {task.request}")

        # Add constraints if any
        if task.constraints:
            prompt_parts.append("\nConstraints:\n- " + "\n- ".join(task.constraints))

        # Add examples if provided
        if task.examples:
            prompt_parts.append("\nExamples:\n" + "\n".join(task.examples[:2]))

        # Language hint
        if task.language:
            prompt_parts.append(f"\nLanguage: {task.language}")

        return "\n".join(prompt_parts)

    def _estimate_cost(self, model: str, tokens: int) -> float:
        """Estimate cost based on model and tokens"""
        # Rough cost estimates per 1M tokens (varies by model)
        cost_per_million = {
            "anthropic/claude-3-haiku": 0.25,
            "anthropic/claude-3-sonnet": 3.00,
            "meta-llama/llama-3.1-8b-instruct": 0.05,
            "mistralai/mistral-7b-instruct": 0.05,
        }

        rate = cost_per_million.get(model, 0.10)
        return (tokens / 1_000_000) * rate

    async def assist(
        self, task: SmartTreeTask, *, cache_scope: str | None = None
    ) -> LLMResponse:
        """Process a task; persistent caching requires a trusted caller scope."""

        # Check cache first
        cache_key = self._get_cache_key(task, cache_scope)
        if cache_scope:
            cached = await run_in_threadpool(self._get_cached_response, cache_key)
            if cached:
                return cached

        # Select appropriate model
        model = self._select_model(task.task_type)

        # Build prompt
        prompt = self._build_prompt(task)

        # Make API request
        try:
            response = await self.client.post(
                "/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": prompt.split("\nTask:")[0]},
                        {
                            "role": "user",
                            "content": "Task:" + prompt.split("\nTask:")[1],
                        },
                    ],
                    "temperature": (
                        0.3
                        if task.task_type in ["code_generation", "refactoring"]
                        else 0.5
                    ),
                    "max_tokens": 2000,
                },
            )
            response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            tokens = data.get("usage", {}).get("total_tokens", 0)

            # Create response
            llm_response = LLMResponse(
                task_id=cache_key,
                model_used=model,
                response=content,
                tokens_used=tokens,
                cost_estimate=self._estimate_cost(model, tokens),
            )

            # Cache the response
            if cache_scope:
                await run_in_threadpool(self._save_to_cache, cache_key, llm_response)

            return llm_response

        except httpx.HTTPError as e:
            # Fallback response on error
            return LLMResponse(
                task_id=cache_key,
                model_used="fallback",
                response=f"Error calling LLM: {e!s}. Please complete this task manually.",
                tokens_used=0,
                cost_estimate=0.0,
            )

    async def batch_assist(
        self, tasks: list[SmartTreeTask], *, cache_scope: str | None = None
    ) -> list[LLMResponse]:
        """Process tasks with the same explicit caller scope, without shared state."""
        # Process up to 5 tasks concurrently
        semaphore = asyncio.Semaphore(5)

        async def process_with_limit(task):
            async with semaphore:
                return await self.assist(task, cache_scope=cache_scope)

        results = await asyncio.gather(
            *[process_with_limit(task) for task in tasks], return_exceptions=True
        )

        # Handle any exceptions
        responses = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                responses.append(
                    LLMResponse(
                        task_id=self._get_cache_key(tasks[i], cache_scope),
                        model_used="error",
                        response=f"Task failed: {result!s}",
                        tokens_used=0,
                        cost_estimate=0.0,
                    )
                )
            else:
                responses.append(result)

        return responses

    async def suggest_improvements(self, file_content: str, file_type: str) -> str:
        """Suggest improvements for a file"""
        task = SmartTreeTask(
            task_type="code_review",
            context=file_content,
            request=f"Review this {file_type} file and suggest 3-5 specific improvements",
            language=file_type,
            constraints=[
                "Be specific",
                "Focus on practical improvements",
                "Keep suggestions brief",
            ],
        )

        response = await self.assist(task)
        return response.response

    async def generate_tests(self, code: str, language: str) -> str:
        """Generate tests for code"""
        task = SmartTreeTask(
            task_type="testing",
            context=code,
            request="Generate comprehensive test cases for this code",
            language=language,
            constraints=[
                "Include edge cases",
                "Use appropriate testing framework",
                "Add comments",
            ],
        )

        response = await self.assist(task)
        return response.response

    async def refactor_code(self, code: str, language: str, goal: str) -> str:
        """Refactor code with specific goal"""
        task = SmartTreeTask(
            task_type="refactoring",
            context=code,
            request=f"Refactor this code to: {goal}",
            language=language,
            constraints=[
                "Maintain functionality",
                "Improve readability",
                "Follow best practices",
            ],
        )

        response = await self.assist(task)
        return response.response

    async def write_documentation(self, code: str, doc_type: str = "readme") -> str:
        """Generate documentation for code"""
        task = SmartTreeTask(
            task_type="documentation",
            context=code,
            request=f"Write a {doc_type} for this code",
            constraints=["Use markdown", "Include examples", "Be concise but complete"],
        )

        response = await self.assist(task)
        return response.response

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


# Singleton instance
_assistant: SmartTreeAssistant | None = None


def get_assistant() -> SmartTreeAssistant:
    """Get or create the assistant instance"""
    global _assistant
    if _assistant is None:
        _assistant = SmartTreeAssistant()
    return _assistant


# Export for use in API
__all__ = [
    "LLMResponse",
    "SmartTreeAssistant",
    "SmartTreeTask",
    "get_assistant",
]
