#!/bin/bash
# Deploy announcements update to f.8t.is 📢

set -e

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Deploying Announcements Feature to f.8t.is${NC}"
echo "==========================================="

echo -e "${YELLOW}📦 SSH into f.8t.is and deploy...${NC}"
echo ""
echo "Run these commands on the server:"
echo ""
echo -e "${BLUE}cd ~/st-aygent${NC}"
echo -e "${BLUE}git pull${NC}"
echo -e "${BLUE}docker-compose -f docker-compose.simple.yml build feedback-api${NC}"
echo -e "${BLUE}docker-compose -f docker-compose.simple.yml up -d feedback-api${NC}"
echo ""
echo -e "${GREEN}✅ Then test the new endpoints:${NC}"
echo ""
echo "# Get announcements for AIs:"
echo -e "${BLUE}curl https://f.8t.is/api/announcements | jq .${NC}"
echo ""
echo "# Get random tips:"
echo -e "${BLUE}curl https://f.8t.is/api/announcements/tips | jq .${NC}"
echo ""
echo "# Create a new announcement (example):"
echo -e "${BLUE}curl -X POST https://f.8t.is/api/announcements \\
  -H 'Content-Type: application/json' \\
  -d '{
    \"id\": \"test-announcement\",
    \"title\": \"Test Announcement\",
    \"message\": \"This is a test announcement for AIs!\",
    \"priority\": \"info\",
    \"targets\": [\"all\"]
  }' | jq .${NC}"
echo ""
echo -e "${YELLOW}📢 Smart Tree AIs can now pull announcements!${NC}"
echo "Aye, Aye! 🚢"