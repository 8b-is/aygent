#!/usr/bin/env python3
"""
Check GitHub token permissions and access
"""

import os
from github import Github
from dotenv import load_dotenv

load_dotenv()

token = os.environ.get('GITHUB_TOKEN')
g = Github(token)

user = g.get_user()
print(f"Authenticated as: {user.login}")
print(f"Name: {user.name}")
print(f"Company: {user.company}")
print(f"Admin: {user.site_admin}")
print(f"Token scopes: {g.oauth_scopes}")

print("\n8b-is Organization Access:")
try:
    org = g.get_organization("8b-is")
    print(f"✅ Can access organization: {org.login}")
    print(f"   Description: {org.description}")
    
    # Check membership
    try:
        membership = org.get_organization_membership(user)
        print(f"   Your role: {membership.role}")
        print(f"   State: {membership.state}")
    except:
        print("   Role: Unable to determine (might be public access only)")
    
    # List repos you can see
    print("\n   Visible repositories:")
    for repo in org.get_repos()[:5]:
        print(f"   - {repo.name}")
    
    # Check if aygent exists
    print("\n   Checking for 'aygent' repository...")
    try:
        repo = org.get_repo("aygent")
        print(f"   ✅ Repository exists: {repo.full_name}")
    except:
        print(f"   ❌ Repository 'aygent' not found")
        print(f"   💡 You need to create it manually or get admin access")
        
except Exception as e:
    print(f"❌ Error accessing organization: {e}")

print("\nOptions:")
print("1. Create the repository manually at: https://github.com/organizations/8b-is/repositories/new")
print("2. Grant admin access to your token/user in the organization settings")
print("3. Use a token from a user with admin rights in 8b-is")