#!/usr/bin/env python3
"""
Check available repositories
"""

import os
from github import Github
from dotenv import load_dotenv

load_dotenv()

token = os.environ.get('GITHUB_TOKEN')
g = Github(token)

print("Current user:", g.get_user().login)
print("\nAccessible repositories:")

# Get all repos the authenticated user can access
for repo in g.get_user().get_repos():
    print(f"  - {repo.full_name}")
    
# Check for 8b-is org repos
print("\nChecking 8b-is organization repos:")
try:
    org = g.get_organization("8b-is")
    for repo in org.get_repos():
        print(f"  - {repo.full_name}")
except Exception as e:
    print(f"  Error accessing 8b-is org: {e}")