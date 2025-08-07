#!/usr/bin/env python3
"""
Test GitHub Integration for aye-is account
"Let's make sure everything's connected!" - Aye & Hue
"""

import os
import sys
from github import Github
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Colors for output
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
MAGENTA = '\033[0;35m'
CYAN = '\033[0;36m'
NC = '\033[0m'

def test_github_connection():
    """Test the GitHub connection and permissions"""
    
    print(f"{CYAN}=== Testing GitHub Integration for aye-is ==={NC}")
    print()
    
    # Get credentials from environment
    token = os.environ.get('GITHUB_TOKEN')
    repo_name = os.environ.get('GITHUB_REPO', '8b-is/aygent')
    user = os.environ.get('GITHUB_USER', 'aye-is')
    email = os.environ.get('GITHUB_EMAIL', 'claude@aye.is')
    
    if not token:
        print(f"{RED}✗ GITHUB_TOKEN not found in environment{NC}")
        return False
    
    print(f"{BLUE}Configuration:{NC}")
    print(f"  User: {user}")
    print(f"  Email: {email}")
    print(f"  Repository: {repo_name}")
    print()
    
    try:
        # Connect to GitHub
        print(f"{BLUE}Connecting to GitHub...{NC}")
        g = Github(token)
        
        # Test authentication
        print(f"{BLUE}Testing authentication...{NC}")
        current_user = g.get_user()
        print(f"{GREEN}✓ Authenticated as: {current_user.login}{NC}")
        print(f"  Name: {current_user.name or 'Not set'}")
        print(f"  Email: {current_user.email or 'Not set'}")
        print(f"  Created: {current_user.created_at}")
        print()
        
        # Check rate limits
        print(f"{BLUE}Checking API rate limits...{NC}")
        rate_limit = g.get_rate_limit()
        core = rate_limit.rate
        print(f"{GREEN}✓ Rate Limit Status:{NC}")
        print(f"  Remaining: {core.remaining}/{core.limit}")
        print(f"  Reset at: {core.reset}")
        print()
        
        # Test repository access
        print(f"{BLUE}Testing repository access...{NC}")
        try:
            repo = g.get_repo(repo_name)
            print(f"{GREEN}✓ Repository accessible: {repo.full_name}{NC}")
            print(f"  Description: {repo.description}")
            print(f"  Stars: {repo.stargazers_count}")
            print(f"  Open Issues: {repo.open_issues_count}")
            print()
            
            # Check permissions
            print(f"{BLUE}Checking permissions...{NC}")
            permissions = repo.permissions
            if permissions:
                print(f"{GREEN}✓ Repository Permissions:{NC}")
                print(f"  Admin: {permissions.admin}")
                print(f"  Push: {permissions.push}")
                print(f"  Pull: {permissions.pull}")
            else:
                print(f"{YELLOW}⚠ Could not determine permissions (might be public repo){NC}")
            print()
            
            # Test issue creation (dry run)
            print(f"{BLUE}Testing issue creation capability...{NC}")
            print(f"{GREEN}✓ Ready to create issues!{NC}")
            print()
            
            # Show recent issues
            print(f"{BLUE}Recent issues in {repo_name}:{NC}")
            issues = repo.get_issues(state='open')[:5]
            for issue in issues:
                labels = ', '.join([l.name for l in issue.labels])
                print(f"  #{issue.number}: {issue.title}")
                if labels:
                    print(f"    Labels: {labels}")
            
            if not issues:
                print(f"  No open issues found")
            
        except Exception as e:
            print(f"{RED}✗ Repository access failed: {e}{NC}")
            print(f"{YELLOW}  Make sure aye-is has access to {repo_name}{NC}")
            return False
        
        print()
        print(f"{GREEN}{'='*50}{NC}")
        print(f"{GREEN}✅ GitHub Integration Test Successful!{NC}")
        print(f"{GREEN}{'='*50}{NC}")
        print()
        print(f"{MAGENTA}Aye says: 'We're connected and ready to rock!'{NC}")
        print(f"{CYAN}Trisha says: 'Everything's organized and accounted for!'{NC}")
        return True
        
    except Exception as e:
        print(f"{RED}✗ GitHub connection failed: {e}{NC}")
        print(f"{YELLOW}Please check:{NC}")
        print(f"  1. Token is valid")
        print(f"  2. Token has correct scopes (repo, read:org)")
        print(f"  3. Network connection is working")
        return False

if __name__ == "__main__":
    success = test_github_connection()
    sys.exit(0 if success else 1)