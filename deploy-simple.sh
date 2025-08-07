#!/bin/bash
# 🚀 Simple deployment to f.8t.is
# Direct deployment using GitHub Container Registry

set -e

SERVER="f.8t.is"
echo "🚀 Deploying ST-AYGENT to ${SERVER}..."

# Copy essential files
echo "📦 Copying files to server..."
scp docker-compose.yml root@${SERVER}:/opt/st-aygent/
scp .env root@${SERVER}:/opt/st-aygent/
scp -r monitoring root@${SERVER}:/opt/st-aygent/
scp -r backup root@${SERVER}:/opt/st-aygent/

# Deploy on server
ssh root@${SERVER} << 'EOF'
cd /opt/st-aygent

echo "🐳 Pulling latest images from ghcr.io..."
docker pull ghcr.io/8b-is/aygent-feedback-api:latest
docker pull ghcr.io/8b-is/aygent-feedback-worker:latest

echo "🔄 Restarting services..."
docker-compose down
docker-compose up -d

echo "✅ Deployment complete!"
docker-compose ps
EOF

echo "🎉 Done! Services available at:"
echo "  API: https://f.8t.is/api"
echo "  Grafana: http://f.8t.is:3000"