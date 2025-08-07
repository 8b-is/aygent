# GitHub Integration Setup for aye-is Account 🚀
*"Let's get Aye properly connected!" - Hue*  
*"Organization is key to success!" - Trisha from Accounting*

## Overview

ST-AYGENT uses the `aye-is` GitHub account to automatically create issues from user feedback. This guide walks through setting up both SSH keys and API tokens for complete integration.

## 1. GitHub Account Setup

### Create the aye-is Account
1. Sign up at GitHub with username: `aye-is`
2. Set profile email to: `claude@aye.is` (or your preferred agent@aye.is)
3. Add profile picture and bio:
   ```
   Name: Aye (ST-AYGENT)
   Bio: Automated feedback processor for 8b-is projects. Part of the Aye & Hue team!
   Location: The Cloud ☁️
   ```

### Add to 8b-is Organization
1. From your main account, go to the 8b-is organization
2. Invite `aye-is` as a member
3. Grant permissions:
   - **Repository Access**: `aygent` repository
   - **Permissions**: Write (to create issues)
   - **Team**: Create "feedback-agents" team if desired

## 2. SSH Key Setup

### Generate SSH Key Pair
```bash
# Generate a dedicated SSH key for aye-is
ssh-keygen -t ed25519 -C "claude@aye.is" -f ~/.ssh/aye-is-github

# This creates:
# - ~/.ssh/aye-is-github (private key)
# - ~/.ssh/aye-is-github.pub (public key)
```

### Add Public Key to GitHub
1. Log into GitHub as `aye-is`
2. Go to Settings → SSH and GPG keys
3. Click "New SSH key"
4. Title: "ST-AYGENT Production Server"
5. Paste contents of `~/.ssh/aye-is-github.pub`

### Configure SSH for Multiple Accounts
Add to `~/.ssh/config`:
```
# Personal GitHub account
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519

# aye-is GitHub account
Host github-aye
  HostName github.com
  User git
  IdentityFile ~/.ssh/aye-is-github
```

Now you can clone using:
```bash
git clone git@github-aye:8b-is/aygent.git
```

## 3. Personal Access Token Setup

### Generate GitHub PAT
1. Log into GitHub as `aye-is`
2. Go to Settings → Developer settings → Personal access tokens → Tokens (classic)
3. Click "Generate new token"
4. Note: "ST-AYGENT Feedback Worker"
5. Select scopes:
   - ✅ `repo` (Full control of private repositories)
   - ✅ `workflow` (Update GitHub Action workflows)
   - ✅ `read:org` (Read org and team membership)
   - ✅ `project` (Full control of projects)
6. Generate token and save it securely

### Token Security Best Practices
- Store in a password manager
- Never commit to repository
- Rotate every 90 days
- Use fine-grained tokens when possible

## 4. Server Deployment Configuration

### For Production Server
Copy the SSH private key to your production server:
```bash
# On your local machine
scp ~/.ssh/aye-is-github aygent@your-server:~/.ssh/

# On the server
chmod 600 ~/.ssh/aye-is-github

# Configure git
git config --global user.name "aye-is"
git config --global user.email "claude@aye.is"
```

### Environment Variables
Update your `.env` file:
```env
# GitHub Configuration
GITHUB_TOKEN=ghp_your_actual_token_here
GITHUB_USER=aye-is
GITHUB_EMAIL=claude@aye.is
GITHUB_REPO=8b-is/aygent

# Agent Identity
AGENT_IDENTITY=claude
AGENT_DOMAIN=aye.is
```

## 5. Docker Configuration

### Add SSH Key to Container
Update `docker-compose.yml`:
```yaml
feedback-worker:
  volumes:
    - ~/.ssh/aye-is-github:/home/app/.ssh/id_rsa:ro
    - ./known_hosts:/home/app/.ssh/known_hosts:ro
```

### Or Use Build Args
In `feedback-worker/Dockerfile`:
```dockerfile
# Accept SSH key as build arg (for private repos)
ARG SSH_PRIVATE_KEY
RUN if [ -n "$SSH_PRIVATE_KEY" ]; then \
    mkdir -p /root/.ssh && \
    echo "$SSH_PRIVATE_KEY" > /root/.ssh/id_rsa && \
    chmod 600 /root/.ssh/id_rsa && \
    ssh-keyscan github.com >> /root/.ssh/known_hosts; \
fi
```

## 6. Email Integration (aye.is domain)

### Email Addresses for Different Agents
Configure email addresses for different contexts:
- `claude@aye.is` - Claude's feedback processing
- `omni@aye.is` - Omni's philosophical insights
- `trisha@aye.is` - Trisha's organizational updates
- `hue@aye.is` - Messages from Hue

### SMTP Configuration
For sending email notifications:
```env
SMTP_HOST=mail.aye.is
SMTP_PORT=587
SMTP_USER=claude@aye.is
SMTP_PASSWORD=your_email_password
SMTP_FROM="Aye (ST-AYGENT) <claude@aye.is>"
```

## 7. Testing the Integration

### Test SSH Connection
```bash
ssh -T git@github-aye
# Should see: "Hi aye-is! You've successfully authenticated..."
```

### Test API Token
```bash
curl -H "Authorization: token ghp_your_token_here" \
     https://api.github.com/user
# Should return aye-is user info
```

### Test Issue Creation
```python
from github import Github

g = Github("ghp_your_token_here")
repo = g.get_repo("8b-is/aygent")
issue = repo.create_issue(
    title="Test Issue from ST-AYGENT",
    body="This is a test issue created by claude@aye.is",
    labels=["feedback", "test"]
)
print(f"Created issue #{issue.number}")
```

## 8. Automation Scripts

### Rotate GitHub Token
Create `scripts/rotate-github-token.sh`:
```bash
#!/bin/bash
# Rotate GitHub token for aye-is account

echo "🔄 Rotating GitHub token for aye-is..."

# Generate new token via GitHub API (requires existing token)
# ... token generation logic ...

# Update .env file
sed -i "s/GITHUB_TOKEN=.*/GITHUB_TOKEN=$NEW_TOKEN/" .env

# Restart services
docker-compose restart feedback-worker

echo "✅ Token rotated successfully!"
```

### Monitor GitHub Rate Limits
Create `scripts/check-github-limits.sh`:
```bash
#!/bin/bash
# Check GitHub API rate limits

curl -s -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/rate_limit | jq .
```

## 9. Security Checklist

- [ ] SSH key has strong passphrase
- [ ] SSH key is backed up securely
- [ ] GitHub token has minimal required scopes
- [ ] Token is stored in environment variables only
- [ ] `.env` file is in `.gitignore`
- [ ] Regular token rotation scheduled
- [ ] 2FA enabled on aye-is account
- [ ] Audit log monitoring enabled

## 10. Troubleshooting

### Permission Denied (SSH)
```bash
# Check SSH key permissions
ls -la ~/.ssh/aye-is-github
# Should be: -rw------- (600)

# Test SSH connection
ssh -vT git@github-aye
```

### API Token Not Working
```bash
# Verify token
curl -I -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com

# Check rate limits
curl -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/rate_limit
```

### Issue Creation Failing
Check worker logs:
```bash
docker-compose logs -f feedback-worker
```

Common issues:
- Token lacks `repo` scope
- Repository permissions insufficient
- Rate limit exceeded
- Network connectivity issues

## Pro Tips from the Team

**Aye says:** "Keep your keys safe and your tokens fresh!"

**Hue notes:** "Test everything in a sandbox repo first!"

**Trisha reminds:** "Document your token expiration dates in your calendar!"

**Omni observes:** "Like waves in the ocean, credentials must flow and renew..."

---

*Remember: Security is a journey, not a destination. Keep your credentials safe and your automation smooth!* 🚢

Aye, Aye! 🚀