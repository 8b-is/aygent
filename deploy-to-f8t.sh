#!/bin/bash
# 🚀 Deploy ST-AYGENT to f.8t.is
# "Deployment with style!" - Trisha from Accounting

set -e

# Colors for our beautiful output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}🚀 ST-AYGENT Deployment Script${NC}"
echo -e "${MAGENTA}Deploying to f.8t.is (Nuremberg)${NC}"
echo ""

# Configuration
SERVER="f.8t.is"
SERVER_USER="root"
DEPLOY_PATH="/opt/st-aygent"

echo -e "${YELLOW}📦 Preparing deployment package...${NC}"

# Create deployment directory
mkdir -p deploy-package

# Copy necessary files
cp -r feedback-api deploy-package/
cp -r feedback-worker deploy-package/
cp docker-compose.yml deploy-package/
cp .env.example deploy-package/
cp -r scripts deploy-package/
cp -r monitoring deploy-package/
cp -r backup deploy-package/

# Create production docker-compose
cat > deploy-package/docker-compose.prod.yml << 'EOF'
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backup:/backup
    networks:
      - feedback-net
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    networks:
      - feedback-net
    healthcheck:
      test: ["CMD", "redis-cli", "--raw", "incr", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  feedback-api:
    image: ghcr.io/8b-is/aygent-feedback-api:latest
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379
      API_KEY: ${FEEDBACK_API_KEY}
      LOG_LEVEL: ${LOG_LEVEL:-info}
      FEEDBACK_DIR: /data/feedback
      STATS_DIR: /data/stats
      CONSENT_DIR: /data/consent
    volumes:
      - feedback_data:/data
    networks:
      - feedback-net
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.feedback-api.rule=Host(`f.8t.is`) && PathPrefix(`/api`)"
      - "traefik.http.routers.feedback-api.tls=true"
      - "traefik.http.routers.feedback-api.tls.certresolver=letsencrypt"
      - "traefik.http.services.feedback-api.loadbalancer.server.port=8000"

  feedback-worker:
    image: ghcr.io/8b-is/aygent-feedback-worker:latest
    restart: unless-stopped
    environment:
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379
      GITHUB_TOKEN: ${GITHUB_TOKEN}
      GITHUB_REPO: ${GITHUB_REPO}
      FEEDBACK_API_URL: http://feedback-api:8000
      WORKER_NAME: ${WORKER_NAME:-worker-1}
      WORKER_CONCURRENCY: ${WORKER_CONCURRENCY:-4}
      BATCH_SIZE: ${BATCH_SIZE:-10}
      PROMETHEUS_PORT: 9090
    networks:
      - feedback-net
    depends_on:
      redis:
        condition: service_healthy
      feedback-api:
        condition: service_started

  prometheus:
    image: prom/prometheus:latest
    restart: unless-stopped
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
    networks:
      - feedback-net
    ports:
      - "9091:9090"

  grafana:
    image: grafana/grafana:latest
    restart: unless-stopped
    environment:
      GF_SECURITY_ADMIN_USER: ${GRAFANA_USER:-admin}
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD}
      GF_INSTALL_PLUGINS: redis-datasource
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./monitoring/grafana/datasources:/etc/grafana/provisioning/datasources
    networks:
      - feedback-net
    ports:
      - "3000:3000"
    depends_on:
      - prometheus

  # Optional Traefik for SSL/routing
  traefik:
    image: traefik:v3.0
    restart: unless-stopped
    command:
      - "--api.insecure=true"
      - "--providers.docker=true"
      - "--providers.docker.exposedbydefault=false"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
      - "--certificatesresolvers.letsencrypt.acme.httpchallenge=true"
      - "--certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=web"
      - "--certificatesresolvers.letsencrypt.acme.email=claude@aye.is"
      - "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json"
    ports:
      - "80:80"
      - "443:443"
      - "8080:8080"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - letsencrypt_data:/letsencrypt
    networks:
      - feedback-net

networks:
  feedback-net:
    driver: bridge

volumes:
  postgres_data:
  redis_data:
  feedback_data:
  prometheus_data:
  grafana_data:
  letsencrypt_data:
EOF

# Create deployment script
cat > deploy-package/setup.sh << 'EOF'
#!/bin/bash
# Setup script for ST-AYGENT on server

set -e

echo "🚀 Setting up ST-AYGENT..."

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | bash
fi

# Install Docker Compose if not present
if ! command -v docker-compose &> /dev/null; then
    echo "Installing Docker Compose..."
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cp .env.example .env
    echo ""
    echo "⚠️  Please edit .env file and add your tokens!"
    echo "    Required: GITHUB_TOKEN, POSTGRES_PASSWORD, REDIS_PASSWORD"
    echo ""
fi

# Create necessary directories
mkdir -p monitoring/grafana/dashboards
mkdir -p monitoring/grafana/datasources
mkdir -p backup

# Pull latest images
echo "Pulling Docker images..."
docker-compose -f docker-compose.prod.yml pull

echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your tokens and passwords"
echo "2. Run: docker-compose -f docker-compose.prod.yml up -d"
echo "3. Access the API at: https://f.8t.is/api"
echo "4. Access Grafana at: http://f.8t.is:3000"
echo ""
EOF

chmod +x deploy-package/setup.sh

# Create tarball
echo -e "${BLUE}📦 Creating deployment package...${NC}"
tar -czf st-aygent-deploy.tar.gz deploy-package/

echo -e "${GREEN}✅ Package created: st-aygent-deploy.tar.gz${NC}"
echo ""

# Deploy to server
echo -e "${YELLOW}🚢 Deploying to ${SERVER}...${NC}"

# Copy package to server
echo -e "${CYAN}Copying package to server...${NC}"
scp st-aygent-deploy.tar.gz ${SERVER_USER}@${SERVER}:/tmp/

# Execute deployment on server
echo -e "${CYAN}Executing deployment...${NC}"
ssh ${SERVER_USER}@${SERVER} << 'ENDSSH'
set -e

# Colors for remote output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}🎯 Remote deployment starting...${NC}"

# Create deployment directory
mkdir -p /opt/st-aygent
cd /opt/st-aygent

# Extract package
echo -e "${YELLOW}Extracting package...${NC}"
tar -xzf /tmp/st-aygent-deploy.tar.gz --strip-components=1

# Run setup
echo -e "${YELLOW}Running setup...${NC}"
bash setup.sh

# Clean up
rm /tmp/st-aygent-deploy.tar.gz

echo -e "${GREEN}✅ Deployment complete on server!${NC}"
echo ""
echo -e "${MAGENTA}📝 Remember to:${NC}"
echo "1. Edit /opt/st-aygent/.env with your tokens"
echo "2. Run: cd /opt/st-aygent && docker-compose -f docker-compose.prod.yml up -d"
echo ""
ENDSSH

# Clean up local files
rm -rf deploy-package
rm st-aygent-deploy.tar.gz

echo ""
echo -e "${GREEN}🎉 Deployment script complete!${NC}"
echo ""
echo -e "${CYAN}Access your services at:${NC}"
echo -e "  ${YELLOW}API:${NC} https://f.8t.is/api"
echo -e "  ${YELLOW}Grafana:${NC} http://f.8t.is:3000"
echo -e "  ${YELLOW}Traefik:${NC} http://f.8t.is:8080"
echo ""
echo -e "${MAGENTA}SSH to server to complete setup:${NC}"
echo -e "  ssh ${SERVER_USER}@${SERVER}"
echo -e "  cd /opt/st-aygent"
echo -e "  vi .env  # Add your tokens"
echo -e "  docker-compose -f docker-compose.prod.yml up -d"
echo ""
echo -e "${CYAN}Aye, Aye! 🚢${NC}"