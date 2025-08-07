#!/usr/bin/env python3
"""
Create ST-AYGENT repository under aye-is account
"""

import os
from github import Github
from dotenv import load_dotenv

load_dotenv()

# Use the PAT to create the repo
token = "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"
g = Github(token)
user = g.get_user()

print(f"Creating repository as: {user.login}")

try:
    # Create the repository under aye-is
    repo = user.create_repo(
        name="st-aygent",
        description="🚀 Smart Tree Feedback System - Automated GitHub issue creation from user feedback. Part of the Aye & Hue ecosystem! Created with love by claude@aye.is",
        private=False,
        has_issues=True,
        has_wiki=True,
        has_downloads=False,
        auto_init=False
    )
    
    print(f"✅ Repository created: {repo.full_name}")
    print(f"   URL: {repo.html_url}")
    print(f"   Clone URL: {repo.ssh_url}")
    
    # Add topics
    repo.replace_topics([
        "feedback-system", 
        "github-automation", 
        "ai-agents", 
        "smart-tree", 
        "aye-is",
        "automation",
        "claude-ai"
    ])
    print("✅ Topics added")
    
    # Create initial labels for feedback categorization
    labels = [
        ("feedback", "0052CC", "User feedback from Smart Tree"),
        ("bug", "d73a4a", "Something isn't working"),
        ("enhancement", "a2eeef", "New feature or request"),
        ("high-priority", "FF0000", "Critical issue needing immediate attention"),
        ("from-ai", "7057ff", "Created by AI agent"),
        ("duplicate", "cfd3d7", "This issue or pull request already exists"),
        ("teleportation", "FEF2C0", "Revolutionary AI features"),
    ]
    
    for name, color, description in labels:
        try:
            repo.create_label(name=name, color=color, description=description)
            print(f"✅ Label created: {name}")
        except:
            pass  # Label might already exist
    
except Exception as e:
    if "already exists" in str(e):
        print(f"Repository already exists under {user.login}")
        repo = user.get_repo("st-aygent")
        print(f"   URL: {repo.html_url}")
        print(f"   SSH URL: {repo.ssh_url}")
    else:
        print(f"Error: {e}")
        exit(1)

print("\n📝 Next steps:")
print("1. Update git remote:")
print(f"   git remote set-url origin git@github-aye:aye-is/st-aygent.git")
print("\n2. Push the code:")
print("   git push -u origin main")
print("\n3. Update .env file:")
print("   GITHUB_REPO=aye-is/st-aygent")