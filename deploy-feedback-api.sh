#!/usr/bin/env bash
# 🚀 Smart Tree Feedback API Deployment to Hetzner
# Your construction helper is deploying to the cloud!

set -euo pipefail

# Colors from Trisha's palette
RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'
PURPLE=$'\033[0;35m'
CYAN=$'\033[0;36m'
NC=$'\033[0m'

print_header() {
    echo ""
    echo "${PURPLE}╔═══════════════════════════════════════════════════════╗${NC}"
    echo "${PURPLE}║       🚀 Smart Tree Feedback API Deployment 🚀        ║${NC}"
    echo "${PURPLE}║         Your Construction Helper Goes Cloud!          ║${NC}"
    echo "${PURPLE}╚═══════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_info() { echo "${BLUE}[INFO]${NC} $1"; }
print_success() { echo "${GREEN}[✓]${NC} $1"; }
print_error() { echo "${RED}[✗]${NC} $1" >&2; }
print_warning() { echo "${YELLOW}[⚠]${NC} $1"; }
print_step() { echo "${CYAN}[STEP $1]${NC} $2"; }

check_requirements() {
    print_step "1" "Checking requirements..."
    
    local missing=()
    
    # Check for required tools
    command -v docker >/dev/null 2>&1 || missing+=("docker")
    command -v hcloud >/dev/null 2>&1 || missing+=("hcloud")
    command -v envsubst >/dev/null 2>&1 || missing+=("envsubst")
    command -v jq >/dev/null 2>&1 || missing+=("jq")
    
    if [ ${#missing[@]} -gt 0 ]; then
        print_error "Missing required tools: ${missing[*]}"
        print_info "Install with: brew install ${missing[*]}"
        exit 1
    fi
    
    # Check for environment variables
    if [ -z "${HETZNER_TOKEN:-}" ]; then
        print_error "HETZNER_TOKEN not set!"
        print_info "Export your Hetzner API token:"
        print_info "  export HETZNER_TOKEN='your-token-here'"
        exit 1
    fi
    
    if [ -z "${GITHUB_TOKEN:-}" ]; then
        print_warning "GITHUB_TOKEN not set - feedback submission may be limited"
    fi
    
    print_success "All requirements met!"
}

build_containers() {
    print_step "2" "Building containers..."
    
    # Build feedback API
    cd feedback-api
    print_info "Building feedback API container..."
    docker build -t ghcr.io/8b-is/smart-tree-feedback-api:latest \
                 -t ghcr.io/8b-is/smart-tree-feedback-api:v4.0.0-alpha .
    
    # Build feedback worker
    cd ../feedback-worker
    print_info "Building feedback worker container..."
    docker build -t ghcr.io/8b-is/smart-tree-feedback-worker:latest \
                 -t ghcr.io/8b-is/smart-tree-feedback-worker:v4.0.0-alpha .
    
    cd ..
    print_success "Containers built successfully!"
}

push_to_registry() {
    print_step "3" "Pushing to GitHub Container Registry..."
    
    # Login to ghcr.io
    if [ -n "${GITHUB_TOKEN:-}" ]; then
        echo "${GITHUB_TOKEN}" | docker login ghcr.io -u USERNAME --password-stdin
    else
        print_warning "Skipping registry push (no GITHUB_TOKEN)"
        return
    fi
    
    # Push images
    docker push ghcr.io/8b-is/smart-tree-feedback-api:latest
    docker push ghcr.io/8b-is/smart-tree-feedback-api:v4.0.0-alpha
    docker push ghcr.io/8b-is/smart-tree-feedback-worker:latest
    docker push ghcr.io/8b-is/smart-tree-feedback-worker:v4.0.0-alpha
    
    print_success "Images pushed to registry!"
}

create_cloud_init() {
    print_step "4" "Preparing cloud-init configuration..."
    
    # Create temporary cloud-init with substituted variables
    export GITHUB_TOKEN="${GITHUB_TOKEN:-}"
    export DISCORD_WEBHOOK="${DISCORD_WEBHOOK:-}"
    export INSTANCE_ID="prod-$(date +%Y%m%d-%H%M%S)"
    
    envsubst < cloud-init/hetzner-feedback-api.yaml > /tmp/cloud-init-api.yaml
    
    print_success "Cloud-init prepared!"
}

deploy_to_hetzner() {
    print_step "5" "Deploying to Hetzner Cloud..."
    
    local SERVER_NAME="smart-tree-feedback-api-prod"
    local SERVER_TYPE="cx11"  # 1 vCPU, 2GB RAM
    local IMAGE="ubuntu-22.04"
    local LOCATION="nbg1"  # Nuremberg, Germany
    
    # Check if server already exists
    if hcloud server describe "$SERVER_NAME" >/dev/null 2>&1; then
        print_warning "Server $SERVER_NAME already exists!"
        read -p "Delete existing server and redeploy? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            print_info "Deleting existing server..."
            hcloud server delete "$SERVER_NAME"
            sleep 5
        else
            print_info "Keeping existing server"
            return
        fi
    fi
    
    # Create new server
    print_info "Creating server: $SERVER_NAME"
    hcloud server create \
        --name "$SERVER_NAME" \
        --type "$SERVER_TYPE" \
        --image "$IMAGE" \
        --location "$LOCATION" \
        --user-data-from-file /tmp/cloud-init-api.yaml \
        --label "service=smart-tree-feedback-api" \
        --label "environment=production" \
        --label "version=v4.0.0-alpha"
    
    # Get server IP
    local SERVER_IP=$(hcloud server ip "$SERVER_NAME")
    
    print_success "Server deployed successfully!"
    echo ""
    echo "${GREEN}═══════════════════════════════════════════════════════${NC}"
    echo "${GREEN}  Deployment Complete! 🎉${NC}"
    echo "${GREEN}═══════════════════════════════════════════════════════${NC}"
    echo ""
    echo "  ${CYAN}Server:${NC} $SERVER_NAME"
    echo "  ${CYAN}IP:${NC} $SERVER_IP"
    echo "  ${CYAN}API URL:${NC} http://$SERVER_IP:8000"
    echo "  ${CYAN}Metrics:${NC} http://$SERVER_IP:9090/metrics"
    echo "  ${CYAN}cAdvisor:${NC} http://$SERVER_IP:8080"
    echo ""
    echo "  ${YELLOW}Note:${NC} Server will be ready in ~2-3 minutes"
    echo ""
    echo "  ${BLUE}SSH Access:${NC}"
    echo "    ssh root@$SERVER_IP"
    echo ""
    echo "  ${BLUE}Check Status:${NC}"
    echo "    ssh root@$SERVER_IP 'docker-compose -f /opt/smart-tree-feedback/docker-compose.yml ps'"
    echo ""
    echo "  ${BLUE}View Logs:${NC}"
    echo "    ssh root@$SERVER_IP 'docker-compose -f /opt/smart-tree-feedback/docker-compose.yml logs -f'"
    echo ""
    
    # Cleanup
    rm -f /tmp/cloud-init-api.yaml
}

setup_dns() {
    print_step "6" "Setting up DNS (optional)..."
    
    print_info "To use a custom domain, add an A record:"
    print_info "  feedback.yourdomain.com -> $(hcloud server ip smart-tree-feedback-api-prod)"
    print_info ""
    print_info "Then update Smart Tree to use your domain:"
    print_info "  export SMART_TREE_FEEDBACK_API=https://feedback.yourdomain.com"
}

main() {
    print_header
    
    # Run deployment steps
    check_requirements
    build_containers
    
    if [ -n "${GITHUB_TOKEN:-}" ]; then
        push_to_registry
    fi
    
    create_cloud_init
    deploy_to_hetzner
    setup_dns
    
    echo ""
    echo "${GREEN}╔═══════════════════════════════════════════════════════╗${NC}"
    echo "${GREEN}║  Your construction helper is now in the cloud! 🏗️☁️   ║${NC}"
    echo "${GREEN}║     Trisha says: 'That's cheaper than coffee!' ☕     ║${NC}"
    echo "${GREEN}╚═══════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Aye, Aye! 🚢"
}

# Handle errors gracefully
trap 'print_error "Deployment failed! Check the logs above."' ERR

# Run if not sourced
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    main "$@"
fi