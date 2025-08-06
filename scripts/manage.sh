#!/bin/bash

# ST-AYGENT Management Script 🚀
# "Making DevOps fun since 2025!" - Trisha from Accounting
# Built with love by Aye & Hue

# Color definitions (because Trisha insists on sparkle! ✨)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
ORANGE='\033[38;5;208m'
PINK='\033[38;5;213m'
NEON_GREEN='\033[38;5;118m'
NEON_BLUE='\033[38;5;51m'
SPARKLE='\033[38;5;226m'
NC='\033[0m' # No Color

# Fancy banner function
print_banner() {
    echo -e "${NEON_BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}   ____  _____      _  __   _______ _____ _   _ _____ ${NC}"
    echo -e "${CYAN}  / ___||_   _|    / \\ \\ \\ / / ____|_   _| \\ | |_   _|${NC}"
    echo -e "${PURPLE}  \\___ \\  | |     / _ \\ \\ V /| |  _|  | | |  \\| | | |  ${NC}"
    echo -e "${PURPLE}   ___) | | |    / ___ \\ | | | |_| |  | | | |\\  | | |  ${NC}"
    echo -e "${PINK}  |____/  |_|   /_/   \\_\\|_|  \\____| |_| |_| \\_| |_|  ${NC}"
    echo -e ""
    echo -e "${SPARKLE}  🎉 Management Script v1.0 - \"Where Aye meets Agent!\" 🎉${NC}"
    echo -e "${NEON_BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
}

# Helper function to print colored messages
print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_sparkle() {
    echo -e "${SPARKLE}✨ $1${NC}"
}

# Check if docker and docker-compose are installed
check_dependencies() {
    print_info "Checking dependencies..."
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed! Please install Docker first."
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed! Please install Docker Compose first."
        exit 1
    fi
    
    print_success "All dependencies are installed!"
}

# Load environment variables
load_env() {
    if [ -f .env ]; then
        print_info "Loading environment variables..."
        # Properly handle .env file with spaces and special characters
        set -a
        source .env
        set +a
        print_success "Environment loaded!"
    else
        print_warning "No .env file found. Using default values."
        print_info "Run './scripts/manage.sh init' to create one from template."
    fi
}

# Initialize project
init_project() {
    print_sparkle "Initializing ST-AYGENT project..."
    
    # Create .env from example if it doesn't exist
    if [ ! -f .env ]; then
        if [ -f .env.example ]; then
            cp .env.example .env
            print_success "Created .env file from template"
            print_warning "Please edit .env and set your configuration values!"
        else
            print_error "No .env.example found! Creating basic .env..."
            create_env_example
            cp .env.example .env
        fi
    fi
    
    # Create necessary directories
    print_info "Creating necessary directories..."
    mkdir -p logs/{api,worker,nginx}
    mkdir -p backups/{postgres,redis,archives}
    mkdir -p ssl
    mkdir -p feedback-api/feedback
    
    print_success "Project initialized!"
    print_info "Next steps:"
    echo "  1. Edit .env file with your configuration"
    echo "  2. Run './scripts/manage.sh up' to start all services"
}

# Create .env.example
create_env_example() {
    cat > .env.example << 'EOF'
# ST-AYGENT Environment Configuration 🔧
# "Configure with style!" - Trisha from Accounting

# ===========================================
# Database Configuration 💾
# ===========================================
POSTGRES_USER=feedback_master
POSTGRES_PASSWORD=super_secret_password_change_me
POSTGRES_DB=feedback_central

# ===========================================
# Redis Configuration 🚀
# ===========================================
REDIS_PASSWORD=redis_secret_password_change_me
REDIS_MAX_MEMORY=256mb

# ===========================================
# API Configuration 🌐
# ===========================================
FEEDBACK_API_KEY=your_secret_api_key_change_me
DEBUG=false
LOG_LEVEL=info

# ===========================================
# Worker Configuration 👷
# ===========================================
GITHUB_TOKEN=ghp_your_github_token_here
GITHUB_REPO=8b-is/st-aygent
WORKER_NAME=worker-1
WORKER_CONCURRENCY=4
BATCH_SIZE=10

# ===========================================
# Monitoring Configuration 📊
# ===========================================
PROMETHEUS_ENABLED=true
GRAFANA_USER=admin
GRAFANA_PASSWORD=change_me_please

# ===========================================
# Backup Configuration 💾
# ===========================================
BACKUP_ENABLED=true
BACKUP_SCHEDULE="0 2 * * *"
BACKUP_RETENTION_DAYS=7
BACKUP_RETENTION_WEEKS=4
BACKUP_RETENTION_MONTHS=12

# S3/MinIO settings (optional)
S3_ENDPOINT=https://s3.amazonaws.com
S3_BUCKET=st-aygent-backups
S3_ACCESS_KEY=your_s3_access_key
S3_SECRET_KEY=your_s3_secret_key
S3_REGION=us-east-1

# Encryption key (32 characters)
BACKUP_ENCRYPTION_KEY=your_32_character_encryption_key

# ===========================================
# Development Tools (optional) 🛠️
# ===========================================
PGADMIN_EMAIL=admin@8b.is
PGADMIN_PASSWORD=pgadmin_password_change_me

# ===========================================
# Hot Tub Mode Settings 🛁
# ===========================================
HOT_TUB_ENABLED=true
HOT_TUB_TEMPERATURE=104  # Fahrenheit, of course!
RUBBER_DUCK_COUNT=3

# Created with 💖 by Aye & Hue
EOF
}

# Start all services
start_services() {
    print_sparkle "Starting all ST-AYGENT services..."
    
    check_dependencies
    load_env
    
    # Pull latest images
    print_info "Pulling latest Docker images..."
    docker-compose pull
    
    # Build custom images
    print_info "Building custom images..."
    docker-compose build
    
    # Start services
    print_info "Starting services..."
    docker-compose up -d
    
    # Wait for services to be healthy
    print_info "Waiting for services to be healthy..."
    sleep 10
    
    # Show status
    show_status
    
    print_success "All services started successfully!"
    print_sparkle "Access points:"
    echo -e "  ${CYAN}📮 Feedback API:${NC} http://localhost:8000/docs"
    echo -e "  ${CYAN}📊 Grafana:${NC} http://localhost:3000 (admin/${GRAFANA_PASSWORD:-admin})"
    echo -e "  ${CYAN}📈 Prometheus:${NC} http://localhost:9090"
    echo -e "  ${CYAN}🐘 pgAdmin:${NC} http://localhost:5050 (run with --profile dev)"
    echo -e "  ${CYAN}🔴 RedisInsight:${NC} http://localhost:8001 (run with --profile dev)"
}

# Stop all services
stop_services() {
    print_warning "Stopping all ST-AYGENT services..."
    docker-compose down
    print_success "All services stopped!"
}

# Restart services
restart_services() {
    print_info "Restarting services..."
    stop_services
    start_services
}

# Show service status
show_status() {
    print_info "Service Status:"
    echo ""
    docker-compose ps
    echo ""
    
    # Check health of critical services
    print_info "Health Checks:"
    
    # Check PostgreSQL
    if docker-compose exec -T postgres pg_isready &> /dev/null; then
        print_success "PostgreSQL is healthy"
    else
        print_error "PostgreSQL is not healthy"
    fi
    
    # Check Redis
    if docker-compose exec -T redis redis-cli ping &> /dev/null; then
        print_success "Redis is healthy"
    else
        print_error "Redis is not healthy"
    fi
    
    # Check API
    if curl -f http://localhost:8000/health &> /dev/null; then
        print_success "Feedback API is healthy"
    else
        print_error "Feedback API is not healthy"
    fi
}

# View logs
view_logs() {
    service=$1
    if [ -z "$service" ]; then
        print_info "Viewing logs for all services (Ctrl+C to exit)..."
        docker-compose logs -f
    else
        print_info "Viewing logs for $service (Ctrl+C to exit)..."
        docker-compose logs -f $service
    fi
}

# Run tests
run_tests() {
    print_sparkle "Running tests (because Trisha insists on quality!)..."
    
    # Test API
    print_info "Testing Feedback API..."
    docker-compose exec feedback-api pytest -v
    
    # Test Worker
    print_info "Testing Feedback Worker..."
    docker-compose exec feedback-worker pytest -v
    
    print_success "All tests completed!"
}

# Generate coverage report
coverage_report() {
    print_info "Generating coverage reports..."
    
    # API coverage
    docker-compose exec feedback-api pytest --cov=. --cov-report=html
    
    # Worker coverage
    docker-compose exec feedback-worker pytest --cov=. --cov-report=html
    
    print_success "Coverage reports generated!"
}

# Backup databases
backup_now() {
    print_sparkle "Creating backup..."
    
    timestamp=$(date +%Y%m%d_%H%M%S)
    backup_dir="backups/manual"
    mkdir -p $backup_dir
    
    # Backup PostgreSQL
    print_info "Backing up PostgreSQL..."
    docker-compose exec -T postgres pg_dumpall -U ${POSTGRES_USER:-postgres} | gzip > "$backup_dir/postgres_backup_$timestamp.sql.gz"
    
    # Backup Redis
    print_info "Backing up Redis..."
    docker-compose exec -T redis redis-cli --raw BGSAVE
    sleep 2
    docker cp st-aygent-redis:/data/dump.rdb "$backup_dir/redis_backup_$timestamp.rdb"
    
    print_success "Backup completed! Files saved in $backup_dir"
}

# Restore from backup
restore_backup() {
    backup_file=$1
    if [ -z "$backup_file" ]; then
        print_error "Please specify a backup file!"
        echo "Usage: ./scripts/manage.sh restore <backup_file>"
        return 1
    fi
    
    print_warning "This will overwrite current data! Are you sure? (yes/no)"
    read -r response
    if [ "$response" != "yes" ]; then
        print_info "Restore cancelled."
        return 0
    fi
    
    print_info "Restoring from $backup_file..."
    
    # Restore PostgreSQL
    if [[ $backup_file == *.sql.gz ]]; then
        gunzip -c $backup_file | docker-compose exec -T postgres psql -U ${POSTGRES_USER:-postgres}
        print_success "PostgreSQL restored!"
    elif [[ $backup_file == *.rdb ]]; then
        docker cp $backup_file st-aygent-redis:/data/dump.rdb
        docker-compose restart redis
        print_success "Redis restored!"
    else
        print_error "Unknown backup file format!"
    fi
}

# Hot Tub Mode! 🛁
hot_tub_mode() {
    print_sparkle "Entering Hot Tub Mode! 🛁"
    echo -e "${CYAN}Temperature: 104°F${NC}"
    echo -e "${BLUE}Bubbles: Maximum${NC}"
    echo -e "${YELLOW}Rubber Ducks: 3 deployed${NC}"
    echo ""
    print_info "Starting collaborative debugging session..."
    
    # Start log streaming in multiple panes (if tmux is available)
    if command -v tmux &> /dev/null; then
        tmux new-session -d -s hottub
        tmux split-window -h
        tmux split-window -v
        tmux select-pane -t 0
        tmux split-window -v
        
        tmux send-keys -t 0 "docker-compose logs -f feedback-api" Enter
        tmux send-keys -t 1 "docker-compose logs -f feedback-worker" Enter
        tmux send-keys -t 2 "docker-compose logs -f nginx" Enter
        tmux send-keys -t 3 "docker-compose logs -f postgres redis" Enter
        
        tmux attach -t hottub
    else
        print_warning "tmux not found. Showing combined logs instead..."
        docker-compose logs -f
    fi
    
    print_sparkle "Exiting Hot Tub Mode. Don't forget your towel! 🏖️"
}

# Clean up everything
cleanup() {
    print_warning "This will remove all containers, volumes, and data!"
    print_warning "Are you absolutely sure? Type 'yes-delete-everything' to confirm:"
    read -r response
    if [ "$response" == "yes-delete-everything" ]; then
        print_info "Cleaning up..."
        docker-compose down -v --remove-orphans
        rm -rf logs/* backups/* postgres-data redis-data
        print_success "Cleanup complete!"
    else
        print_info "Cleanup cancelled. Phew! 😅"
    fi
}

# Development mode
dev_mode() {
    print_sparkle "Starting in development mode..."
    docker-compose --profile dev up -d
    print_success "Development services started!"
    print_info "Additional services available:"
    echo -e "  ${CYAN}🐘 pgAdmin:${NC} http://localhost:5050"
    echo -e "  ${CYAN}🔴 RedisInsight:${NC} http://localhost:8001"
}

# Main script logic
case "$1" in
    up|start)
        print_banner
        start_services
        ;;
    down|stop)
        print_banner
        stop_services
        ;;
    restart)
        print_banner
        restart_services
        ;;
    status|ps)
        print_banner
        show_status
        ;;
    logs)
        print_banner
        view_logs $2
        ;;
    init)
        print_banner
        init_project
        ;;
    test)
        print_banner
        run_tests
        ;;
    test-api)
        print_banner
        docker-compose exec feedback-api pytest -v
        ;;
    test-worker)
        print_banner
        docker-compose exec feedback-worker pytest -v
        ;;
    coverage)
        print_banner
        coverage_report
        ;;
    backup|backup-now)
        print_banner
        backup_now
        ;;
    restore|restore-backup)
        print_banner
        restore_backup $2
        ;;
    hot-tub)
        print_banner
        hot_tub_mode
        ;;
    dev)
        print_banner
        dev_mode
        ;;
    cleanup|clean)
        print_banner
        cleanup
        ;;
    setup-backups)
        print_banner
        print_info "Automated backups are configured in docker-compose.yml"
        print_success "Backups will run according to BACKUP_SCHEDULE in .env"
        ;;
    *)
        print_banner
        print_error "Unknown command: $1"
        echo ""
        print_info "Available commands:"
        echo -e "  ${GREEN}up/start${NC}        - Start all services"
        echo -e "  ${GREEN}down/stop${NC}       - Stop all services"
        echo -e "  ${GREEN}restart${NC}         - Restart all services"
        echo -e "  ${GREEN}status/ps${NC}       - Show service status"
        echo -e "  ${GREEN}logs [service]${NC}  - View logs (all or specific service)"
        echo -e "  ${GREEN}init${NC}            - Initialize project"
        echo -e "  ${GREEN}test${NC}            - Run all tests"
        echo -e "  ${GREEN}test-api${NC}        - Run API tests only"
        echo -e "  ${GREEN}test-worker${NC}     - Run worker tests only"
        echo -e "  ${GREEN}coverage${NC}        - Generate coverage reports"
        echo -e "  ${GREEN}backup${NC}          - Create manual backup"
        echo -e "  ${GREEN}restore <file>${NC}  - Restore from backup"
        echo -e "  ${GREEN}hot-tub${NC}         - Enter Hot Tub Mode 🛁"
        echo -e "  ${GREEN}dev${NC}             - Start with dev tools"
        echo -e "  ${GREEN}cleanup${NC}         - Remove everything (careful!)"
        echo ""
        print_sparkle "Built with love by Aye & Hue!"
        exit 1
        ;;
esac

# Trisha's parting wisdom
if [ $? -eq 0 ]; then
    fortunes=(
        "Remember: A well-organized codebase is a happy codebase!"
        "Pro tip: Always backup before you hack up!"
        "Debugging is just like accounting - follow the numbers!"
        "Keep calm and docker-compose up!"
        "May your logs be clean and your metrics green!"
    )
    fortune=${fortunes[$RANDOM % ${#fortunes[@]}]}
    echo ""
    print_sparkle "Trisha says: $fortune"
fi