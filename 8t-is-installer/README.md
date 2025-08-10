# 8t.is - Smart-Tree Installer

Universal installer for smart-tree that automatically detects browsers vs terminals.

## Features

- **Smart Detection**: Automatically serves HTML to browsers, installer script to terminals
- **Interactive Installation**: Guides users through OS detection, install location, and MCP setup  
- **MCP Integration**: Auto-configures for Claude Code with preauthorization
- **Multi-Platform**: Supports Linux (x64/ARM), macOS (Intel/Apple Silicon), Windows
- **Shell Integration**: Configures PATH and optional aliases

## Usage

### Terminal Install
```bash
curl 8t.is | sh
```

### Non-Interactive Install
```bash
curl 8t.is | sh -s -- --non-interactive
```

### Browser Access
Navigate to https://8t.is for the web interface

## Routes

- `/` - Main route (auto-detects browser vs terminal)
- `/install` - Alias for main route
- `/tree` - Alias for main route  
- `/releases/*` - Direct download links

## MCP Features

The installer automatically:
- Creates MCP server wrapper at `~/.config/smart-tree/mcp/`
- Configures Claude Code with preauthorization if detected
- Sets up `alwaysAllow` permissions for read/list operations
- Backs up existing MCP configurations before modifying

## Deployment

### Docker
```bash
docker-compose up -d
```

### Manual
Serve with nginx/caddy using the provided configs on port 8424.

## Configuration

Port: **8424** (8b-is standard for dev/container websites)

Made with 💜 by 8b-is