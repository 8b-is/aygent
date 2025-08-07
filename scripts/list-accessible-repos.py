#!/usr/bin/env python3
"""
List all repositories accessible by the current token
"""

import os
from github import Github
from dotenv import load_dotenv

load_dotenv()

token = os.environ.get('GITHUB_TOKEN')
g = Github(token)

user = g.get_user()
print(f"Authenticated as: {user.login}")
print(f"Token scopes: {g.oauth_scopes}")
print("\nSearching for aygent repositories...")

# Search for repos with 'aygent' in the name
repos_found = []
for repo in g.search_repositories("aygent"):
    if "aygent" in repo.name.lower():
        repos_found.append(repo.full_name)
        print(f"  - {repo.full_name} (public)")
        if len(repos_found) >= 10:
            break

# Try to list 8b-is org repos
print("\nTrying to access 8b-is organization repos...")
try:
    # Try through search
    for repo in g.search_repositories("org:8b-is"):
        print(f"  - {repo.full_name}")
        if repo.name == "aygent":
            print(f"    ✅ Found aygent repo!")
except Exception as e:
    print(f"  Error: {e}")

# Check if it's a private repo issue
print("\nTrying direct access to 8b-is/aygent...")
try:
    repo = g.get_repo("8b-is/aygent")
    print(f"✅ Direct access successful: {repo.full_name}")
    print(f"   Private: {repo.private}")
    print(f"   Visibility: {repo.visibility if hasattr(repo, 'visibility') else 'unknown'}")
except Exception as e:
    print(f"❌ Direct access failed: {e}")

print("\nNote: The token might need the 'repo' scope for private repos or 'public_repo' for public repos")