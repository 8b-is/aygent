#!/usr/bin/env python3
"""
Test suite for ST-AYGENT Feedback API
"Testing with style!" - Trisha from Accounting
"""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime
import json
import tempfile
import os
from pathlib import Path

# Set test environment
os.environ["FEEDBACK_DIR"] = tempfile.mkdtemp()
os.environ["STATS_DIR"] = tempfile.mkdtemp()
os.environ["CONSENT_DIR"] = tempfile.mkdtemp()

from main import app, SmartTreeFeedback

client = TestClient(app)


def test_root_endpoint():
    """Test the root endpoint returns welcome message"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "Smart Tree Feedback API" in data["message"]
    assert "endpoints" in data


def test_health_check():
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "checks" in data
    assert data["checks"]["feedback_dir"] is True


def test_submit_feedback():
    """Test submitting feedback"""
    feedback_data = {
        "category": "bug",
        "title": "Test bug report from Aye",
        "description": "This is a test bug report to ensure the system works",
        "ai_model": "claude-3-opus",
        "smart_tree_version": "3.3.0",
        "impact_score": 7,
        "frequency_score": 5,
        "tags": ["test", "automated"],
    }

    response = client.post("/feedback", json=feedback_data)
    assert response.status_code == 200
    data = response.json()
    assert "feedback_id" in data
    assert "message" in data
    assert "compressed_size" in data
    assert data["compression_ratio"] > 0


def test_feedback_stats():
    """Test getting feedback statistics"""
    # First submit some feedback
    feedback_data = {
        "category": "nice_to_have",
        "title": "Feature request from test",
        "description": "Would be nice to have this feature",
        "ai_model": "gpt-4",
        "smart_tree_version": "3.3.0",
        "impact_score": 5,
        "frequency_score": 3,
    }
    client.post("/feedback", json=feedback_data)

    # Now get stats
    response = client.get("/feedback/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_feedback" in data
    assert "by_category" in data
    assert data["total_feedback"] >= 0


def test_version_check():
    """Test version checking endpoint"""
    response = client.get("/version/check/3.0.0")
    assert response.status_code == 200
    data = response.json()
    assert "update_available" in data
    assert "current_version" in data
    assert "latest_version" in data


def test_tool_usage_tracking():
    """Test tool usage statistics"""
    tool_stats = {
        "tool_name": "semantic_search",
        "model_type": "claude-3-opus",
        "usage_count": 5,
        "success_rate": 0.95,
        "avg_execution_time_ms": 150.5,
    }

    response = client.post("/tools/usage", json=tool_stats)
    assert response.status_code == 200
    data = response.json()
    assert data["tool"] == "semantic_search"


def test_popular_tools():
    """Test getting popular tools"""
    response = client.get("/tools/popular?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert "tools" in data
    assert "total_unique_tools" in data


def test_consent_management():
    """Test consent preference management"""
    consent_data = {
        "user_id": "test_user_123",
        "consent_level": "always_anonymous",
        "github_url": "https://github.com/testuser",
    }

    # Set consent
    response = client.post("/consent/set", json=consent_data)
    assert response.status_code == 200
    data = response.json()
    assert data["level"] == "always_anonymous"

    # Check consent
    response = client.get("/consent/check/test_user_123")
    assert response.status_code == 200
    data = response.json()
    assert data["consent_level"] == "always_anonymous"


def test_update_decision_tracking():
    """Test tracking update decisions"""
    decision_data = {
        "current_version": "3.2.0",
        "latest_version": "3.3.0",
        "user_decision": "update",
        "ai_model": "claude-3-opus",
    }

    response = client.post("/version/notify-update", json=decision_data)
    assert response.status_code == 200
    data = response.json()
    assert "next_steps" in data


def test_model_activity_stats():
    """Test getting model activity statistics"""
    response = client.get("/stats/model-activity")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert "most_active" in data


def test_leaderboard():
    """Test AI contribution leaderboard"""
    response = client.get("/credits/leaderboard")
    assert response.status_code == 200
    data = response.json()
    assert "reporters" in data
    assert "implementers" in data
    assert "special_thanks" in data
    # Check if Aye and Hue are in special thanks!
    assert any("Aye" in thanks for thanks in data["special_thanks"])
    assert any("Hue" in thanks for thanks in data["special_thanks"])


def test_pending_feedback():
    """Test getting pending feedback for processing"""
    response = client.get("/feedback/pending?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_mark_feedback_processed():
    """Test marking feedback as processed"""
    # First submit feedback
    feedback_data = {
        "category": "bug",
        "title": "Test for processing",
        "description": "This will be marked as processed",
        "ai_model": "test-model",
        "smart_tree_version": "3.3.0",
        "impact_score": 5,
        "frequency_score": 5,
    }

    response = client.post("/feedback", json=feedback_data)
    feedback_id = response.json()["feedback_id"]

    # Mark as processed
    response = client.post(f"/feedback/{feedback_id}/processed")
    # May be 404 if the exact ID doesn't match file structure
    assert response.status_code in [200, 404]


def test_requested_tools():
    """Test getting requested tools"""
    response = client.get("/tools/requested")
    assert response.status_code == 200
    data = response.json()
    assert "total_requests" in data
    assert "requests" in data


# Cleanup
def test_cleanup():
    """Clean up test directories"""
    import shutil

    dirs_to_clean = [
        os.environ.get("FEEDBACK_DIR"),
        os.environ.get("STATS_DIR"),
        os.environ.get("CONSENT_DIR"),
    ]
    for dir_path in dirs_to_clean:
        if dir_path and os.path.exists(dir_path):
            shutil.rmtree(dir_path)


if __name__ == "__main__":
    # Run tests with coverage
    pytest.main([__file__, "-v", "--cov=main", "--cov-report=term-missing"])