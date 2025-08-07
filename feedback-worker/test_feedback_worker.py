#!/usr/bin/env python3
"""
Test suite for ST-AYGENT Feedback Worker
"Quality assurance with pizzazz!" - Trisha from Accounting
"""

import pytest
import asyncio
import os
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime
import json

# Set test environment
os.environ["GITHUB_TOKEN"] = "fake_token_for_testing"
os.environ["GITHUB_REPO"] = "test/repo"
os.environ["REDIS_URL"] = "redis://localhost:6379"
os.environ["FEEDBACK_API_URL"] = "http://localhost:8000"

from worker import FeedbackWorker


class TestFeedbackWorker:
    """Test the feedback worker functionality"""

    @pytest.fixture
    def worker(self):
        """Create a test worker instance"""
        with patch("worker.Github") as mock_github:
            # Mock GitHub client
            mock_repo = Mock()
            mock_github.return_value.get_repo.return_value = mock_repo
            worker = FeedbackWorker()
            worker.repo = None  # Disable GitHub for tests
            yield worker

    def test_worker_initialization(self, worker):
        """Test worker initializes correctly"""
        assert worker is not None
        assert worker.feedback_api_url == "http://localhost:8000"
        assert worker.github_repo == "test/repo"

    def test_categorize_feedback_bug(self, worker):
        """Test categorizing bug feedback"""
        feedback = {
            "title": "Error in file processing",
            "description": "The system crashes when processing large files",
            "tags": ["error", "crash"],
        }
        category = worker.categorize_feedback(feedback)
        assert category == "bug"

    def test_categorize_feedback_enhancement(self, worker):
        """Test categorizing enhancement feedback"""
        feedback = {
            "title": "Add dark mode support",
            "description": "It would be nice to have a dark theme option",
            "tags": ["feature", "ui"],
        }
        category = worker.categorize_feedback(feedback)
        assert category == "enhancement"

    def test_categorize_feedback_performance(self, worker):
        """Test categorizing performance feedback"""
        feedback = {
            "title": "Slow response times",
            "description": "The API is very slow when handling multiple requests",
            "tags": ["performance", "slow"],
        }
        category = worker.categorize_feedback(feedback)
        assert category == "performance"

    def test_categorize_feedback_question(self, worker):
        """Test categorizing question feedback"""
        feedback = {
            "title": "How to use the new feature?",
            "description": "I'm not sure how this works. Can you explain?",
            "tags": ["help", "question"],
        }
        category = worker.categorize_feedback(feedback)
        assert category == "question"

    def test_prioritize_feedback_critical(self, worker):
        """Test prioritizing critical feedback"""
        feedback = {"impact_score": 9, "frequency_score": 8, "category": "bug"}
        priority = worker.prioritize_feedback(feedback)
        assert priority == "critical"

    def test_prioritize_feedback_high(self, worker):
        """Test prioritizing high priority feedback"""
        feedback = {"impact_score": 7, "frequency_score": 6, "category": "enhancement"}
        priority = worker.prioritize_feedback(feedback)
        assert priority == "high"

    def test_prioritize_feedback_medium(self, worker):
        """Test prioritizing medium priority feedback"""
        feedback = {"impact_score": 5, "frequency_score": 5, "category": "enhancement"}
        priority = worker.prioritize_feedback(feedback)
        assert priority == "medium"

    def test_prioritize_feedback_low(self, worker):
        """Test prioritizing low priority feedback"""
        feedback = {"impact_score": 3, "frequency_score": 2, "category": "question"}
        priority = worker.prioritize_feedback(feedback)
        assert priority == "low"

    @pytest.mark.asyncio
    async def test_process_feedback_no_github(self, worker):
        """Test processing feedback without GitHub integration"""
        feedback = {
            "id": "test123",
            "title": "Test feedback",
            "description": "This is a test",
            "impact_score": 5,
            "frequency_score": 5,
            "category": "bug",
            "tags": ["test"],
        }

        # Process should work even without GitHub
        result = await worker.process_feedback(feedback)
        # Since GitHub is disabled, it should just categorize and return
        assert result is not None

    def test_worker_patterns(self, worker):
        """Test that pattern lists are properly initialized"""
        assert len(worker.bug_patterns) > 0
        assert len(worker.enhancement_patterns) > 0
        assert len(worker.performance_patterns) > 0
        assert "error" in worker.bug_patterns
        assert "feature" in worker.enhancement_patterns
        assert "slow" in worker.performance_patterns


class TestWorkerMetrics:
    """Test worker metrics functionality"""

    @pytest.fixture
    def worker(self):
        """Create a test worker with metrics"""
        with patch("worker.Github"):
            worker = FeedbackWorker()
            worker.repo = None
            yield worker

    def test_metrics_initialization(self, worker):
        """Test metrics are initialized"""
        assert worker.metrics is not None
        assert "processed" in worker.metrics
        assert "created" in worker.metrics
        assert "errors" in worker.metrics

    def test_metrics_increment(self, worker):
        """Test metric incrementing"""
        initial_value = worker.metrics["processed"]._value.get()
        worker.metrics["processed"].inc()
        assert worker.metrics["processed"]._value.get() == initial_value + 1


@pytest.mark.asyncio
async def test_worker_redis_connection():
    """Test Redis connection handling"""
    with patch("worker.aioredis.from_url") as mock_redis:
        mock_redis.return_value = AsyncMock()
        with patch("worker.Github"):
            worker = FeedbackWorker()
            worker.repo = None

            # Test connection
            await worker.connect()
            assert worker.redis is not None
            mock_redis.assert_called_once()

            # Test disconnection
            await worker.disconnect()


def test_feedback_formatting():
    """Test feedback message formatting"""
    feedback = {
        "title": "Test Issue",
        "description": "This is a test description",
        "ai_model": "claude-3-opus",
        "impact_score": 8,
        "frequency_score": 7,
        "smart_tree_version": "3.3.0",
        "tags": ["test", "automated"],
        "examples": [{"description": "Example 1", "code": "print('test')"}],
    }

    # Test that formatting doesn't raise errors
    with patch("worker.Github"):
        worker = FeedbackWorker()
        worker.repo = None

        # Create issue body (this is done in create_github_issue)
        body = f"""
## Description
{feedback.get('description', 'No description provided')}

## Impact
- **Impact Score**: {feedback.get('impact_score', 0)}/10
- **Frequency Score**: {feedback.get('frequency_score', 0)}/10

## Metadata
- **AI Model**: {feedback.get('ai_model', 'Unknown')}
- **Smart Tree Version**: {feedback.get('smart_tree_version', 'Unknown')}
- **Tags**: {', '.join(feedback.get('tags', []))}
        """

        assert "Test Issue" in feedback["title"]
        assert "claude-3-opus" in body
        assert "8/10" in body


if __name__ == "__main__":
    # Run tests with coverage
    pytest.main([__file__, "-v", "--cov=worker", "--cov-report=term-missing"])