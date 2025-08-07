#!/usr/bin/env python3
"""
Test script for feedback worker
"""

import asyncio
import os
import pytest
import httpx

# Use production API if CI environment, otherwise local
API_BASE_URL = "https://f.8t.is/api" if os.getenv("CI") else "http://localhost:8422"


@pytest.mark.asyncio
async def test_feedback_submission():
    """Test submitting feedback to the API"""

    test_feedback = {
        "category": "bug",
        "title": "[TEST] Search results don't show line content",
        "description": "When using search_in_files MCP tool, it only shows file paths and match counts, not the actual matching lines. This makes it hard to understand context without opening files.",
        "affected_command": "st --search 'TODO'",
        "mcp_tool": "search_in_files",
        "examples": [
            {
                "description": "Current output lacks context",
                "code": "search_in_files(path='/project', keyword='TODO')",
                "expected_output": "Should show: filename:line_number: actual line content with TODO",
            }
        ],
        "proposed_solution": "Add line content to search results with configurable context lines (like grep -C)",
        "ai_model": "claude-3-opus",
        "smart_tree_version": "3.3.5",
        "impact_score": 8,
        "frequency_score": 9,
        "tags": ["mcp", "search", "usability", "ci-test"],
        "auto_fixable": True,
        "fix_complexity": "simple",
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Submit feedback
            response = await client.post(
                f"{API_BASE_URL}/feedback",
                json=test_feedback,
                headers={"X-MCP-Client": "ci-test-script"},
            )

            if response.status_code == 200:
                result = response.json()
                print("✅ Feedback submitted successfully!")
                print(f"   ID: {result['feedback_id']}")
                print(f"   Compression: {result['compression_ratio']:.1f}x")
                return result["feedback_id"]
            else:
                print(f"❌ Failed to submit feedback: {response.status_code}")
                print(f"   {response.text}")
                return None
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        if os.getenv("CI"):
            # In CI, skip if production API is not available
            pytest.skip(f"Production API not available in CI: {e}")
        else:
            raise


@pytest.mark.asyncio
async def test_pending_endpoint():
    """Test fetching pending feedback"""

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{API_BASE_URL}/feedback/pending?limit=5")

            if response.status_code == 200:
                items = response.json()
                print(f"\n📋 Found {len(items)} pending feedback items")
                for item in items:
                    print(
                        f"   - [{item['category']}] {item['title']} (impact: {item['impact_score']})"
                    )
            else:
                print(f"❌ Failed to fetch pending: {response.status_code}")
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        if os.getenv("CI"):
            # In CI, skip if production API is not available
            pytest.skip(f"Production API not available in CI: {e}")
        else:
            raise


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("CI") == "true", reason="Worker metrics not available in CI"
)
async def test_worker_metrics():
    """Check worker metrics"""

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("http://localhost:9090/metrics")
            if response.status_code == 200:
                print("\n📊 Worker metrics available")
                # Parse some key metrics
                for line in response.text.split("\n"):
                    if "feedback_processed_total" in line and not line.startswith("#"):
                        print(f"   {line.strip()}")
            else:
                print("⚠️  Worker metrics not available (worker not running?)")
        except httpx.ConnectError:
            print("⚠️  Cannot connect to worker (not running?)")


async def main():
    """Run all tests"""

    print("🧪 Testing Smart Tree Feedback System\n")

    # Test 1: Submit feedback
    feedback_id = await test_feedback_submission()

    # Test 2: Check pending
    await test_pending_endpoint()

    # Test 3: Check worker metrics
    await test_worker_metrics()

    print("\n✨ Tests complete!")

    if feedback_id:
        print("\nTo see the worker process this feedback:")
        print("  1. Start Redis: docker run -d -p 6379:6379 redis:7-alpine")
        print("  2. Set GITHUB_TOKEN environment variable")
        print("  3. Run worker: python worker.py")
        print("  4. Check GitHub issues at: https://github.com/8b-is/smart-tree/issues")


if __name__ == "__main__":
    asyncio.run(main())
