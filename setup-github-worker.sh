#!/bin/bash
# Setup GitHub Integration for Feedback Worker 🤖

set -e

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}🔧 GitHub Worker Setup${NC}"
echo "======================="
echo ""
echo -e "${YELLOW}This script will help you set up the GitHub integration for the feedback worker.${NC}"
echo ""

# Check if .env exists
ENV_FILE=".env"
if [ -f "$ENV_FILE" ]; then
    echo -e "${BLUE}Found existing .env file${NC}"
    source "$ENV_FILE"
fi

# Prompt for GitHub token if not set
if [ -z "$GITHUB_TOKEN" ]; then
    echo -e "${YELLOW}📝 GitHub Personal Access Token Setup${NC}"
    echo ""
    echo "To create issues and trigger workflows, you need a GitHub token with these permissions:"
    echo "  • repo (Full control of private repositories)"
    echo "  • workflow (Update GitHub Action workflows)"
    echo ""
    echo "Create one at: https://github.com/settings/tokens/new"
    echo ""
    read -p "Enter your GitHub Personal Access Token: " GITHUB_TOKEN
    echo ""
fi

# Set default values
GITHUB_USER=${GITHUB_USER:-"8b-is"}
GITHUB_EMAIL=${GITHUB_EMAIL:-"claude@8b.is"}
GITHUB_REPO=${GITHUB_REPO:-"8b-is/aygent"}
FEEDBACK_API_URL=${FEEDBACK_API_URL:-"http://feedback-api:8420"}
REDIS_URL=${REDIS_URL:-"redis://redis:6379"}

# Create .env file
cat > "$ENV_FILE" << EOF
# GitHub Integration
GITHUB_TOKEN=$GITHUB_TOKEN
GITHUB_USER=$GITHUB_USER
GITHUB_EMAIL=$GITHUB_EMAIL
GITHUB_REPO=$GITHUB_REPO

# API Configuration
FEEDBACK_API_URL=$FEEDBACK_API_URL
REDIS_URL=$REDIS_URL

# Prometheus Metrics
PROMETHEUS_PORT=9090
EOF

echo -e "${GREEN}✅ Created .env file with configuration${NC}"
echo ""

# Create docker-compose override for local development
cat > docker-compose.override.yml << 'EOF'
version: '3.8'

services:
  feedback-worker:
    env_file:
      - .env
    environment:
      - GITHUB_TOKEN=${GITHUB_TOKEN}
      - GITHUB_USER=${GITHUB_USER}
      - GITHUB_EMAIL=${GITHUB_EMAIL}
      - GITHUB_REPO=${GITHUB_REPO}
EOF

echo -e "${GREEN}✅ Created docker-compose.override.yml for local development${NC}"
echo ""

# Test GitHub token
echo -e "${YELLOW}🔍 Testing GitHub token...${NC}"
RESPONSE=$(curl -s -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user)

if echo "$RESPONSE" | grep -q '"login"'; then
    USERNAME=$(echo "$RESPONSE" | grep -o '"login":"[^"]*' | cut -d'"' -f4)
    echo -e "${GREEN}✅ Token valid! Authenticated as: $USERNAME${NC}"
else
    echo -e "${RED}❌ Invalid token or authentication failed${NC}"
    exit 1
fi

# Check repository access
echo -e "${YELLOW}🔍 Checking repository access...${NC}"
REPO_RESPONSE=$(curl -s -H "Authorization: token $GITHUB_TOKEN" "https://api.github.com/repos/$GITHUB_REPO")

if echo "$REPO_RESPONSE" | grep -q '"full_name"'; then
    echo -e "${GREEN}✅ Can access repository: $GITHUB_REPO${NC}"
else
    echo -e "${RED}❌ Cannot access repository: $GITHUB_REPO${NC}"
    echo "Make sure the token has 'repo' scope and you have access to the repository"
    exit 1
fi

echo ""
echo -e "${GREEN}🎉 Setup Complete!${NC}"
echo ""
echo "Next steps:"
echo -e "${BLUE}1. Start the worker with GitHub integration:${NC}"
echo "   docker-compose up -d feedback-worker"
echo ""
echo -e "${BLUE}2. Monitor the worker logs:${NC}"
echo "   docker-compose logs -f feedback-worker"
echo ""
echo -e "${BLUE}3. The worker will now:${NC}"
echo "   • Create GitHub issues from feedback"
echo "   • Trigger AI fix workflows for high-impact bugs"
echo "   • Track duplicates and metrics"
echo ""
echo -e "${YELLOW}📢 AI Fix Dispatch will trigger for:${NC}"
echo "   • Category: 'bug' or 'critical'"
echo "   • Impact score: 7 or higher"
echo "   • Will create a branch and draft PR automatically"
echo ""
echo "Aye, Aye! 🚢"