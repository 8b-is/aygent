#!/usr/bin/env python3
"""
Test creating an issue in 8b-is/aygent
"""

import os
from github import Github
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

token = os.environ.get('GITHUB_TOKEN')
repo_name = os.environ.get('GITHUB_REPO', '8b-is/aygent')
# Use auth=Auth.Token for fine-grained PATs
from github import Github, Auth
auth = Auth.Token(token)
g = Github(auth=auth)

print(f"Authenticated as: {g.get_user().login}")

try:
    # Try different ways to access the repo
    print(f"\nTrying to access {repo_name}...")
    
    # Method 1: Direct repo access
    try:
        repo = g.get_repo(repo_name)
        print(f"✅ Found repository: {repo.full_name}")
    except:
        # Method 2: Through organization
        org = g.get_organization("8b-is")
        repo = org.get_repo("aygent")
        print(f"✅ Found repository through org: {repo.full_name}")
    
    # Create a test issue
    print("\nCreating test issue...")
    
    issue_title = f"🧪 Test Issue from ST-AYGENT - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    issue_body = """## This is a test issue from the ST-AYGENT Feedback System

**Created by:** claude@aye.is
**Purpose:** Testing GitHub integration

### Test Details
- ✅ Authentication working
- ✅ Repository access confirmed
- ✅ Issue creation successful

### Next Steps
This issue can be closed as it's just a test.

---
*Automatically created by claude@aye.is*
*ST-AYGENT Feedback System*

Aye, Aye! 🚢
"""
    
    issue = repo.create_issue(
        title=issue_title,
        body=issue_body,
        labels=["feedback", "test", "from-ai"]
    )
    
    print(f"✅ Issue created successfully!")
    print(f"   Number: #{issue.number}")
    print(f"   URL: {issue.html_url}")
    print(f"   State: {issue.state}")
    
    print("\n🎉 GitHub integration is working perfectly!")
    print(f"The feedback worker can now create issues in {repo_name}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    print("\nTroubleshooting:")
    print("1. Make sure the token has 'repo' scope")
    print("2. Verify the user has access to 8b-is organization")
    print("3. Check if the repository exists and is accessible")