#!/usr/bin/env python3
"""
Verify permissions and create repository
"""

import os
import time
from github import Github
from dotenv import load_dotenv

load_dotenv()

token = os.environ.get('GITHUB_TOKEN')
g = Github(token)

user = g.get_user()
print(f"Authenticated as: {user.login}")

# Force refresh to get latest permissions
print("\nChecking organization membership (refreshed)...")
try:
    # Get fresh org object
    org = g.get_organization("8b-is")
    
    # Try to get members (only works with proper permissions)
    print(f"Organization: {org.login}")
    
    # Check if we can see private repos (indicates member access)
    all_repos = list(org.get_repos(type='all'))
    public_repos = list(org.get_repos(type='public'))
    print(f"Can see {len(all_repos)} total repos ({len(public_repos)} public)")
    
    # Try creating with a fresh token state
    print("\nAttempting to create repository...")
    try:
        repo = org.create_repo(
            name="aygent",
            description="🚀 ST-AYGENT: Smart Tree Feedback System - Automated GitHub issue creation from user feedback. Part of the Aye & Hue ecosystem!",
            homepage="https://aye.is",
            private=False,
            has_issues=True,
            has_wiki=True,
            has_projects=True,
            has_downloads=True,
            auto_init=False
        )
        
        print(f"✅ Repository created successfully!")
        print(f"   Name: {repo.full_name}")
        print(f"   URL: {repo.html_url}")
        print(f"   SSH: {repo.ssh_url}")
        
        # Add topics
        print("\nAdding topics...")
        repo.replace_topics([
            "feedback-system",
            "github-automation",
            "ai-agents",
            "smart-tree",
            "aye-is",
            "claude-ai",
            "automation"
        ])
        print("✅ Topics added")
        
        # Create labels
        print("\nCreating labels...")
        labels = [
            ("feedback", "0052CC", "User feedback from Smart Tree"),
            ("bug", "d73a4a", "Something isn't working"),
            ("enhancement", "a2eeef", "New feature or request"),
            ("high-priority", "FF0000", "Critical issue needing immediate attention"),
            ("from-ai", "7057ff", "Created by AI agent (claude@aye.is)"),
            ("duplicate", "cfd3d7", "This issue or pull request already exists"),
            ("question", "d876e3", "Further information is requested"),
            ("performance", "FBCA04", "Performance improvements"),
        ]
        
        for name, color, description in labels:
            try:
                repo.create_label(name=name, color=color, description=description)
                print(f"   ✅ Label created: {name}")
            except Exception as e:
                if "already_exists" in str(e):
                    print(f"   ⚠️ Label already exists: {name}")
                else:
                    print(f"   ❌ Failed to create label {name}: {e}")
        
        print("\n" + "="*50)
        print("🎉 SUCCESS! Repository is ready!")
        print("="*50)
        print("\nNow push your code:")
        print("  git push -u origin main")
        print("\nThe feedback worker can now create issues at:")
        print(f"  {repo.html_url}")
        
    except Exception as e:
        if "already exists" in str(e).lower():
            print("✅ Repository already exists at 8b-is/aygent")
            repo = org.get_repo("aygent")
            print(f"   URL: {repo.html_url}")
            print("\nYou can push your code with:")
            print("  git push -u origin main")
        else:
            print(f"❌ Failed to create repository: {e}")
            print("\nThe token might need to be regenerated with the new permissions.")
            print("Try creating a new token at: https://github.com/settings/tokens/new")
            
except Exception as e:
    print(f"Error: {e}")