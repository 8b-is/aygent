#!/usr/bin/env python3
"""
Create aygent repository in 8b-is organization
"""

import os
from github import Github
from dotenv import load_dotenv

load_dotenv()

token = os.environ.get('GITHUB_TOKEN')
g = Github(token)

print(f"Authenticated as: {g.get_user().login}")

try:
    # Get the 8b-is organization
    org = g.get_organization("8b-is")
    print(f"✅ Found organization: {org.login}")
    
    # Create the repository
    repo = org.create_repo(
        name="aygent",
        description="🚀 ST-AYGENT: Smart Tree Feedback System - Automated GitHub issue creation from user feedback. Part of the Aye & Hue ecosystem!",
        private=False,
        has_issues=True,
        has_wiki=True,
        has_projects=True,
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
        "automation"
    ])
    print("✅ Topics added")
    
    # Create labels
    labels = [
        ("feedback", "0052CC", "User feedback from Smart Tree"),
        ("bug", "d73a4a", "Something isn't working"),
        ("enhancement", "a2eeef", "New feature or request"),
        ("high-priority", "FF0000", "Critical issue"),
        ("from-ai", "7057ff", "Created by AI agent"),
        ("duplicate", "cfd3d7", "This issue already exists"),
    ]
    
    for name, color, description in labels:
        try:
            repo.create_label(name=name, color=color, description=description)
            print(f"✅ Label created: {name}")
        except:
            pass
    
    print("\n📝 Now push the code:")
    print("   git push -u origin main")
    
except Exception as e:
    print(f"Error: {e}")
    if "already exists" in str(e).lower():
        print("Repository already exists!")
    elif "must have admin rights" in str(e).lower():
        print("You need admin rights in the 8b-is organization to create repos")