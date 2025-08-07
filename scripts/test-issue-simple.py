#!/usr/bin/env python3
"""
Simple test for creating GitHub issues
"""

import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

token = os.environ.get('GITHUB_TOKEN')
repo = os.environ.get('GITHUB_REPO', '8b-is/aygent')

print(f"Creating issue in {repo}...")

# Create issue data
issue_data = {
    "title": f"🎉 Test Issue from ST-AYGENT - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    "body": """## This is a test issue from the ST-AYGENT Feedback System

**Created by:** claude@aye.is
**Purpose:** Testing GitHub integration with mega token

### Test Details
- ✅ Authentication working
- ✅ Repository access confirmed
- ✅ Issue creation successful

### System Info
- Token type: Fine-grained PAT (mega token)
- Repository: 8b-is/aygent
- Agent: claude@aye.is

### Next Steps
This issue can be closed as it's just a test.

---
*Automatically created by claude@aye.is*
*ST-AYGENT Feedback System*

Aye, Aye! 🚢""",
    "labels": ["feedback", "test", "from-ai"]
}

# Make API call
headers = {
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github.v3+json",
    "Content-Type": "application/json"
}

response = requests.post(
    f"https://api.github.com/repos/{repo}/issues",
    json=issue_data,
    headers=headers
)

if response.status_code == 201:
    issue = response.json()
    print(f"✅ Issue created successfully!")
    print(f"   Number: #{issue['number']}")
    print(f"   URL: {issue['html_url']}")
    print(f"   Title: {issue['title']}")
    print("\n🎉 GitHub integration is working perfectly!")
    print(f"The feedback worker can now create issues in {repo}")
else:
    print(f"❌ Failed to create issue")
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")