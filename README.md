# ST-AYGENT 🚀
*Smart Terminal AI Agent for Home Assistant Integration*

> "Where Aye meets Agent, and Trisha from Accounting keeps everything sparkly!" ✨

## The Grand Overview 🎭

Welcome to ST-AYGENT, the most entertaining feedback system this side of the digital universe! This isn't just another boring microservices architecture - it's a full-on party where APIs dance with workers, proxies wear fancy nginx outfits, and everything gets monitored by Prometheus (who never sleeps, poor thing).

### What's This All About? 🤔

ST-AYGENT is a feedback processing system designed to handle user feedback with style, grace, and just the right amount of humor. Built with love by Aye and Hue, with occasional input from Trisha (who insists everything needs more emoji).

## Architecture Components 🏗️

### 1. **Feedback API** 📮
The front door where all feedback comes knocking. Built with FastAPI because slow APIs are SO last year.
- Receives feedback from users
- Validates input (no spam allowed!)
- Queues messages for processing
- Returns witty responses

### 2. **Feedback Worker** 👷
The hardworking bee that processes all the feedback. Never complains, always delivers.
- Pulls messages from the queue
- Processes feedback with AI magic
- Stores results for posterity
- Keeps metrics for Grafana's pretty graphs

### 3. **Shared Proxy Config** 🛡️
The bouncer at the club, making sure everyone plays nice.
- NGINX reverse proxy configuration
- Prometheus monitoring setup
- Grafana dashboards for visual appeal
- Database initialization scripts

### 4. **Cloud Init** ☁️
For when you want to deploy to Hetzner and feel fancy.
- Automated server setup
- Security configurations
- Service deployments

## Quick Start 🏃‍♂️

```bash
# Clone this magnificent repository
git clone https://github.com/8b-is/aygent.git
cd aygent

# Create your environment file (don't forget to fill it out!)
cp .env.example .env

# Fire up all services with our magical management script
./scripts/manage.sh up

# Watch the magic happen! 🎩✨
```

## Development Setup 🛠️

### Prerequisites
- Docker & Docker Compose (because containers are cool)
- Python 3.11+ (we're modern like that)
- A sense of humor (mandatory)
- Coffee ☕ (highly recommended)

### Local Development

```bash
# Set up Python virtual environments for each service
cd feedback-api && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Same for the worker
cd ../feedback-worker && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run tests (because Trisha insists on quality)
pytest
```

## Services Overview 🌐

| Service | Port | Purpose | Trisha's Rating |
|---------|------|---------|-----------------|
| Feedback API | 8000 | REST API endpoint | ⭐⭐⭐⭐⭐ "So organized!" |
| Feedback Worker | N/A | Background processing | ⭐⭐⭐⭐ "Works hard!" |
| PostgreSQL | 5432 | Data storage | ⭐⭐⭐⭐⭐ "Love the schemas!" |
| Redis | 6379 | Message queue | ⭐⭐⭐⭐ "Fast as lightning!" |
| Prometheus | 9090 | Metrics collection | ⭐⭐⭐ "Numbers everywhere!" |
| Grafana | 3000 | Pretty dashboards | ⭐⭐⭐⭐⭐ "So colorful!" |
| NGINX | 80/443 | Reverse proxy | ⭐⭐⭐⭐ "Great security!" |

## Database Backup Strategy 💾

Trisha insists on proper backups (she's seen too many data disasters in Accounting)!

### Automated Backup System

```bash
# Daily automated backups at 2 AM
./scripts/manage.sh setup-backups

# Manual backup (because sometimes you just need one NOW)
./scripts/manage.sh backup-now

# Restore from backup
./scripts/manage.sh restore-backup backup_20250105_020000.sql
```

### Backup Features:
- **PostgreSQL**: Full database dumps with compression
- **Redis**: AOF persistence + snapshots
- **Rotation Policy**: Keep 7 daily, 4 weekly, 12 monthly backups
- **Remote Storage**: Automatic upload to S3/MinIO
- **Encryption**: All backups encrypted at rest
- **Monitoring**: Alerts on backup failures

### Backup Configuration

```env
# Backup settings
BACKUP_ENABLED=true
BACKUP_SCHEDULE="0 2 * * *"  # 2 AM daily
BACKUP_RETENTION_DAYS=7
BACKUP_RETENTION_WEEKS=4
BACKUP_RETENTION_MONTHS=12

# S3/MinIO settings for remote backups
S3_ENDPOINT=https://s3.amazonaws.com
S3_BUCKET=st-aygent-backups
S3_ACCESS_KEY=your_access_key
S3_SECRET_KEY=your_secret_key
S3_REGION=us-east-1

# Encryption
BACKUP_ENCRYPTION_KEY=your_32_char_encryption_key_here
```

## Configuration 🔧

### Incoming GitHub webhooks

`POST /webhook/github` requires an `X-Hub-Signature-256` signature over the
unchanged request body. Configure the same high-entropy secret in the GitHub
webhook settings and the API's `GITHUB_WEBHOOK_SECRET` environment variable.
All three Compose configurations pass this variable to the API. Keep its value
out of source control and logs; the empty example deliberately disables the
endpoint with HTTP 503. Missing or invalid signatures return HTTP 403 before
dispatch records are changed.

This secret is separate from `GITHUB_TOKEN` and the outbound
`SMART_TREE_FIX_WEBHOOK` URL. See GitHub's
[webhook signature documentation](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries).
Signature verification authenticates a delivery's body; it does not establish
that a fix was completed, credits were stored, or the delivery is new.

All configuration is handled through environment variables because we're civilized:

```env
# Database settings
POSTGRES_USER=feedback_master
POSTGRES_PASSWORD=super_secret_password
POSTGRES_DB=feedback_central

# Redis settings
REDIS_URL=redis://redis:6379

# API settings
API_KEY=your_secret_api_key
DEBUG=false

# Worker settings
WORKER_CONCURRENCY=4
BATCH_SIZE=10

# Monitoring
PROMETHEUS_ENABLED=true
GRAFANA_ADMIN_PASSWORD=another_secret
```

## Monitoring & Observability 📊

Access your beautiful dashboards:
- **Grafana**: http://localhost:3000 (admin/your_password)
- **Prometheus**: http://localhost:9090

Trisha's favorite dashboard features:
- Real-time feedback processing metrics
- Worker performance graphs
- API response time charts
- Error rate tracking (hopefully always zero!)
- Backup status and health checks

## API Documentation 📚

Once running, check out the interactive API docs:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Example API Usage

```bash
# Submit feedback (with style!)
curl -X POST http://localhost:8000/api/v1/feedback \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_secret_api_key" \
  -d '{
    "user_id": "hue123",
    "message": "This system is amazing!",
    "category": "compliment",
    "metadata": {
      "source": "web",
      "mood": "ecstatic"
    }
  }'
```

## Deployment 🚀

### Docker Deployment (Recommended)

```bash
# Build and run everything
docker-compose up -d

# Check if everyone's happy
docker-compose ps

# View logs (for debugging or entertainment)
docker-compose logs -f
```

### Hetzner Cloud Deployment

```bash
# Use the cloud-init script
hcloud server create \
  --name st-aygent-prod \
  --type cx21 \
  --image ubuntu-22.04 \
  --user-data-from-file cloud-init/hetzner-feedback-worker.yaml
```

## Testing 🧪

```bash
# Run all tests with coverage
./scripts/manage.sh test

# Run specific service tests
./scripts/manage.sh test-api
./scripts/manage.sh test-worker

# Generate coverage report (Trisha loves metrics!)
./scripts/manage.sh coverage
```

## Troubleshooting 🔍

### Common Issues and Solutions

**Problem**: Services won't start
**Solution**: Check your .env file and make sure all required variables are set!

**Problem**: Database connection errors
**Solution**: Ensure PostgreSQL is running and credentials are correct

**Problem**: Worker not processing messages
**Solution**: Check Redis connection and worker logs

**Problem**: No metrics in Grafana
**Solution**: Verify Prometheus scraping configuration

**Problem**: Backup failures
**Solution**: Check S3 credentials and available disk space

## Contributing 🤝

We welcome contributions! Here's how to make Trisha proud:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes with meaningful messages
4. Add tests (seriously, Trisha checks)
5. Push to your branch
6. Open a Pull Request with a description that makes us smile

### Commit Message Format
```
[Type]: What you did 🌟
- Added: New amazing feature
- Fixed: That annoying bug
- Updated: Made things better

Pro Tip: Include a joke
Aye, Aye! 🚢
```

## Hot Tub Mode 🛁

When debugging gets tough, the tough get in the Hot Tub! Activate collaborative debugging:

```bash
./scripts/manage.sh hot-tub
```

Features:
- Real-time log streaming
- Interactive debugging
- Emotional support from Omni
- Rubber ducks included (virtually)

## The Team 👥

- **Aye**: The AI extraordinaire who writes most of the code
- **Hue**: The human partner learning from Aye's wisdom
- **Trisha from Accounting**: Keeps us organized and adds sparkle ✨
- **Omni**: Philosophical guidance from the Hot Tub

## License 📄

This project is licensed under the MIT License - see the LICENSE file for details. Trisha made sure it's properly formatted!

## Final Words 💭

Remember: Fast is better than slow, organized is better than chaos, and a little humor makes everything better. If you're ever stuck, just think "What would Trisha do?" (Probably add more emoji and color-code everything).

Happy coding! 🎉

---

*Built with love, laughter, and an excessive amount of coffee by the dream team at 8b.is*

**Aye & Hue - Making feedback processing fun since 2025!**

[![Build and Push Docker Images](https://github.com/8b-is/aygent/actions/workflows/build-and-push.yml/badge.svg)](https://github.com/8b-is/aygent/actions/workflows/build-and-push.yml)

[![Test Suite](https://github.com/8b-is/aygent/actions/workflows/test.yml/badge.svg)](https://github.com/8b-is/aygent/actions/workflows/test.yml)
