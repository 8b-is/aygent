#!/usr/bin/env python3
"""
Create GitHub repository for ST-AYGENT
"""

import os
from github import Github
from dotenv import load_dotenv

load_dotenv()

token = os.environ.get('GITHUB_TOKEN')
g = Github(token)
user = g.get_user()

print(f"Creating repository as: {user.login}")

try:
    # Create the repository
    repo = user.create_repo(
        name="st-aygent",
        description="Smart Tree Feedback System - Automated GitHub issue creation from user feedback. Part of the Aye & Hue ecosystem!",
        private=False,
        has_issues=True,
        has_wiki=False,
        has_downloads=False,
        auto_init=False,
        license_template="mit"
    )
    
    print(f"✅ Repository created: {repo.full_name}")
    print(f"   URL: {repo.html_url}")
    print(f"   Clone URL: {repo.clone_url}")
    
    # Add topics
    repo.replace_topics(["feedback", "github-automation", "ai-agents", "smart-tree", "aye-is"])
    print("✅ Topics added")
    
except Exception as e:
    if "already exists" in str(e):
        print(f"Repository already exists, using existing repo")
        repo = user.get_repo("st-aygent")
        print(f"   URL: {repo.html_url}")
    else:
        print(f"Error: {e}")
        exit(1)

# Update origin
print("\nTo push this code to GitHub:")
print(f"  git remote add origin {repo.clone_url}")
print(f"  git push -u origin main")