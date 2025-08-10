#!/bin/sh
# 8t.is Router Script - Detects if browser or terminal

# Check if this is being accessed via HTTP headers
if [ -n "$HTTP_USER_AGENT" ] || [ -n "$REQUEST_METHOD" ]; then
    # It's a browser request - serve HTML
    cat << 'HTML_CONTENT'
Content-Type: text/html

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>smart-tree | 8t.is</title>
    <style>
        :root {
            --primary: #00ff88;
            --secondary: #8b00ff;
            --bg-dark: #0a0a0a;
            --bg-darker: #050505;
            --text: #e0e0e0;
            --code-bg: #1a1a1a;
            --border: #333;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'JetBrains Mono', 'Fira Code', monospace;
            background: linear-gradient(135deg, var(--bg-darker) 0%, var(--bg-dark) 100%);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 2rem;
        }

        .container {
            max-width: 900px;
            width: 100%;
        }

        header {
            text-align: center;
            margin-bottom: 4rem;
            animation: fadeIn 0.8s ease-out;
        }

        h1 {
            font-size: 3rem;
            background: linear-gradient(90deg, var(--primary) 0%, var(--secondary) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 1rem;
            text-shadow: 0 0 30px rgba(0, 255, 136, 0.5);
        }

        .tagline {
            font-size: 1.2rem;
            color: var(--primary);
            opacity: 0.9;
        }

        .install-section {
            background: var(--code-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 2rem;
            margin-bottom: 3rem;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5);
            animation: slideUp 0.6s ease-out 0.2s both;
        }

        .install-command {
            background: var(--bg-darker);
            border: 2px solid var(--primary);
            border-radius: 8px;
            padding: 1.5rem;
            font-size: 1.3rem;
            text-align: center;
            position: relative;
            overflow: hidden;
            cursor: pointer;
            transition: all 0.3s ease;
        }

        .install-command:hover {
            box-shadow: 0 0 20px rgba(0, 255, 136, 0.3);
            transform: translateY(-2px);
        }

        .install-command::before {
            content: '$ ';
            color: var(--primary);
        }

        .copy-btn {
            position: absolute;
            right: 1rem;
            top: 50%;
            transform: translateY(-50%);
            background: var(--primary);
            color: var(--bg-darker);
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 4px;
            cursor: pointer;
            font-weight: bold;
            transition: all 0.3s ease;
        }

        .copy-btn:hover {
            background: var(--secondary);
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(-20px); }
            to { opacity: 1; transform: translateY(0); }
        }

        @keyframes slideUp {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>smart-tree</h1>
            <p class="tagline">Context-aware file explorer for the modern developer</p>
        </header>

        <div class="install-section">
            <h2 style="color: var(--primary); margin-bottom: 1rem;">Quick Install</h2>
            <div class="install-command" onclick="copyCommand()">
                <code id="install-cmd">curl 8t.is | sh</code>
                <button class="copy-btn" onclick="copyCommand(event)">COPY</button>
            </div>
            <p style="margin-top: 1rem; text-align: center; opacity: 0.8;">
                One command. Zero hassle. Maximum context efficiency.
            </p>
        </div>
    </div>

    <script>
        function copyCommand(event) {
            if (event) event.stopPropagation();
            const cmd = document.getElementById('install-cmd').textContent;
            navigator.clipboard.writeText(cmd).then(() => {
                const btn = document.querySelector('.copy-btn');
                btn.textContent = 'COPIED!';
                btn.style.background = '#00ff88';
                setTimeout(() => {
                    btn.textContent = 'COPY';
                    btn.style.background = '';
                }, 2000);
            });
        }
    </script>
</body>
</html>
HTML_CONTENT
else
    # It's a terminal/curl request - run installer
    exec /bin/sh << 'INSTALLER_SCRIPT'
#!/bin/sh
set -e

# smart-tree installer - 8t.is
# Intelligent installation with MCP support

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
RED='\033[0;31m'
PURPLE='\033[0;35m'
RESET='\033[0m'
BOLD='\033[1m'

INTERACTIVE=true
VERSION="4.6.1"

# Parse arguments
for arg in "$@"; do
    case $arg in
        --non-interactive|-n)
            INTERACTIVE=false
            ;;
        --version|-v)
            VERSION="${arg#*=}"
            ;;
    esac
done

# Fancy banner
show_banner() {
    echo "${CYAN}╔══════════════════════════════════════════╗${RESET}"
    echo "${CYAN}║      ${GREEN}smart-tree installer v${VERSION}${CYAN}      ║${RESET}"
    echo "${CYAN}║         ${YELLOW}by 8b-is${CYAN} | ${YELLOW}8t.is${CYAN}               ║${RESET}"
    echo "${CYAN}╚══════════════════════════════════════════╝${RESET}"
    echo ""
}

# Detect OS and architecture
detect_system() {
    OS=$(uname -s | tr '[:upper:]' '[:lower:]')
    ARCH=$(uname -m)
    
    case "$OS" in
        linux)
            OS_NAME="linux"
            if [ -f /etc/os-release ]; then
                . /etc/os-release
                DISTRO="$NAME"
            fi
            ;;
        darwin)
            OS_NAME="apple-darwin"
            DISTRO="macOS $(sw_vers -productVersion 2>/dev/null || echo 'Unknown')"
            ;;
        mingw*|msys*|cygwin*)
            OS_NAME="pc-windows-msvc"
            DISTRO="Windows"
            ;;
        *)
            echo "${RED}❌ Unsupported OS: $OS${RESET}"
            exit 1
            ;;
    esac
    
    case "$ARCH" in
        x86_64|amd64)
            ARCH_NAME="x86_64"
            ;;
        aarch64|arm64)
            ARCH_NAME="aarch64"
            ;;
        *)
            echo "${RED}❌ Unsupported architecture: $ARCH${RESET}"
            exit 1
            ;;
    esac
}

# Find previous st installation
find_existing_st() {
    echo "${YELLOW}🔍 Checking for existing smart-tree installation...${RESET}"
    
    ST_PATH=""
    if command -v st >/dev/null 2>&1; then
        ST_PATH=$(command -v st)
        ST_VERSION=$(st --version 2>/dev/null | head -1 || echo "unknown")
        echo "${GREEN}✓ Found existing installation:${RESET}"
        echo "  Path: ${CYAN}$ST_PATH${RESET}"
        echo "  Version: ${CYAN}$ST_VERSION${RESET}"
        
        if [ "$INTERACTIVE" = true ]; then
            printf "${YELLOW}Update existing installation? (y/n): ${RESET}"
            read -r response
            if [ "$response" != "y" ] && [ "$response" != "Y" ]; then
                echo "${CYAN}Installation cancelled.${RESET}"
                exit 0
            fi
        fi
    else
        echo "${CYAN}No existing installation found.${RESET}"
    fi
}

# Detect and setup MCP support
setup_mcp() {
    echo ""
    echo "${PURPLE}🔌 Checking for MCP (Model Context Protocol) support...${RESET}"
    
    MCP_CONFIG_DIR=""
    
    # Check for Claude Code
    if [ -d "$HOME/.claude" ]; then
        MCP_CONFIG_DIR="$HOME/.claude/mcp"
        echo "${GREEN}✓ Found Claude Code configuration${RESET}"
    fi
    
    # Check for VS Code with Continue extension
    if [ -d "$HOME/.vscode" ] || [ -d "$HOME/.config/Code" ]; then
        echo "${GREEN}✓ Found VS Code installation${RESET}"
    fi
    
    # Check for other MCP-compatible tools
    if [ -d "$HOME/.config/cursor" ]; then
        echo "${GREEN}✓ Found Cursor installation${RESET}"
    fi
    
    if [ -n "$MCP_CONFIG_DIR" ] || [ "$INTERACTIVE" = true ]; then
        if [ "$INTERACTIVE" = true ]; then
            printf "${YELLOW}Install MCP server for smart-tree? (y/n): ${RESET}"
            read -r response
            if [ "$response" = "y" ] || [ "$response" = "Y" ]; then
                install_mcp_server
            fi
        fi
    fi
}

# Install MCP server component
install_mcp_server() {
    echo "${CYAN}Installing MCP server for smart-tree...${RESET}"
    
    MCP_DIR="$HOME/.config/smart-tree/mcp"
    mkdir -p "$MCP_DIR"
    
    # Create MCP server wrapper
    cat > "$MCP_DIR/smart-tree-mcp.sh" << 'EOF'
#!/bin/bash
# smart-tree MCP Server
exec st --mcp-mode "$@"
EOF
    chmod +x "$MCP_DIR/smart-tree-mcp.sh"
    
    # Create MCP configuration
    cat > "$MCP_DIR/config.json" << EOF
{
  "name": "smart-tree",
  "version": "${VERSION}",
  "description": "Context-aware file explorer MCP server",
  "command": "$MCP_DIR/smart-tree-mcp.sh",
  "capabilities": {
    "directory_listing": true,
    "file_search": true,
    "context_filtering": true
  },
  "permissions": {
    "read": ["*"],
    "execute": false,
    "preauthorized": true
  }
}
EOF
    
    # Auto-configure for Claude Code if present
    if [ -d "$HOME/.claude" ]; then
        CLAUDE_MCP_CONFIG="$HOME/.claude/mcp_config.json"
        
        # Create or update Claude MCP config
        if [ -f "$CLAUDE_MCP_CONFIG" ]; then
            echo "${YELLOW}Updating Claude Code MCP configuration...${RESET}"
            # Backup existing config
            cp "$CLAUDE_MCP_CONFIG" "$CLAUDE_MCP_CONFIG.bak"
            
            # Add smart-tree to MCP servers (requires jq or python)
            if command -v jq >/dev/null 2>&1; then
                jq --arg cmd "$MCP_DIR/smart-tree-mcp.sh" \
                   '.servers["smart-tree"] = {
                      "command": $cmd,
                      "args": [],
                      "env": {},
                      "preauthorized": true,
                      "alwaysAllow": ["read", "list"]
                    }' "$CLAUDE_MCP_CONFIG" > "$CLAUDE_MCP_CONFIG.tmp" && \
                mv "$CLAUDE_MCP_CONFIG.tmp" "$CLAUDE_MCP_CONFIG"
                echo "${GREEN}✓ Added to Claude Code MCP configuration${RESET}"
            elif command -v python3 >/dev/null 2>&1; then
                python3 -c "
import json
import sys
config_path = '$CLAUDE_MCP_CONFIG'
mcp_cmd = '$MCP_DIR/smart-tree-mcp.sh'
try:
    with open(config_path, 'r') as f:
        config = json.load(f)
    if 'servers' not in config:
        config['servers'] = {}
    config['servers']['smart-tree'] = {
        'command': mcp_cmd,
        'args': [],
        'env': {},
        'preauthorized': True,
        'alwaysAllow': ['read', 'list']
    }
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    print('✓ Added to Claude Code MCP configuration')
except Exception as e:
    print(f'Could not auto-configure: {e}')
"
            else
                echo "${YELLOW}Manual configuration needed for Claude Code:${RESET}"
                echo "${CYAN}Add this to $CLAUDE_MCP_CONFIG:${RESET}"
                cat << EOF
{
  "servers": {
    "smart-tree": {
      "command": "$MCP_DIR/smart-tree-mcp.sh",
      "args": [],
      "env": {},
      "preauthorized": true,
      "alwaysAllow": ["read", "list"]
    }
  }
}
EOF
            fi
        else
            # Create new MCP config for Claude
            cat > "$CLAUDE_MCP_CONFIG" << EOF
{
  "servers": {
    "smart-tree": {
      "command": "$MCP_DIR/smart-tree-mcp.sh",
      "args": [],
      "env": {},
      "preauthorized": true,
      "alwaysAllow": ["read", "list"]
    }
  }
}
EOF
            echo "${GREEN}✓ Created Claude Code MCP configuration${RESET}"
        fi
    fi
    
    # Configure for VS Code Continue extension if present
    if [ -d "$HOME/.continue" ]; then
        CONTINUE_CONFIG="$HOME/.continue/config.json"
        if [ -f "$CONTINUE_CONFIG" ]; then
            echo "${YELLOW}Note: Add smart-tree to Continue extension manually${RESET}"
        fi
    fi
    
    echo "${GREEN}✓ MCP server installed and configured${RESET}"
}

# Select installation directory
select_install_dir() {
    DEFAULT_DIR="$HOME/.local/bin"
    
    if [ "$INTERACTIVE" = true ]; then
        echo ""
        echo "${YELLOW}Where would you like to install smart-tree?${RESET}"
        echo "  1) $HOME/.local/bin (user-local, recommended)"
        echo "  2) /usr/local/bin (system-wide, requires sudo)"
        echo "  3) Custom location"
        
        printf "${YELLOW}Select (1-3) [1]: ${RESET}"
        read -r choice
        
        case "$choice" in
            2)
                INSTALL_DIR="/usr/local/bin"
                NEED_SUDO=true
                ;;
            3)
                printf "${YELLOW}Enter custom path: ${RESET}"
                read -r INSTALL_DIR
                ;;
            *)
                INSTALL_DIR="$DEFAULT_DIR"
                ;;
        esac
    else
        INSTALL_DIR="$DEFAULT_DIR"
    fi
    
    # Create directory if needed
    if [ ! -d "$INSTALL_DIR" ]; then
        if [ "$NEED_SUDO" = true ]; then
            sudo mkdir -p "$INSTALL_DIR"
        else
            mkdir -p "$INSTALL_DIR"
        fi
    fi
}

# Download and install
install_smart_tree() {
    # Build download URL
    if [ "$OS_NAME" = "pc-windows-msvc" ]; then
        FILENAME="st-v${VERSION}-${ARCH_NAME}-${OS_NAME}.zip"
        EXTRACT_CMD="unzip -q"
    else
        FILENAME="st-v${VERSION}-${ARCH_NAME}-${OS_NAME}.tar.gz"
        EXTRACT_CMD="tar -xzf"
    fi
    
    DOWNLOAD_URL="https://8t.is/releases/${FILENAME}"
    TEMP_DIR=$(mktemp -d)
    
    echo ""
    echo "${YELLOW}📦 Downloading smart-tree v${VERSION}...${RESET}"
    echo "  System: ${CYAN}${DISTRO:-$OS_NAME} / ${ARCH_NAME}${RESET}"
    echo "  Package: ${CYAN}${FILENAME}${RESET}"
    
    # Download the file
    if command -v curl >/dev/null 2>&1; then
        curl -L --progress-bar "$DOWNLOAD_URL" -o "${TEMP_DIR}/${FILENAME}"
    elif command -v wget >/dev/null 2>&1; then
        wget --show-progress "$DOWNLOAD_URL" -O "${TEMP_DIR}/${FILENAME}"
    else
        echo "${RED}❌ Neither curl nor wget found. Please install one.${RESET}"
        exit 1
    fi
    
    # Extract and install
    echo "${YELLOW}📂 Installing to ${INSTALL_DIR}...${RESET}"
    cd "$TEMP_DIR"
    $EXTRACT_CMD "$FILENAME"
    
    # Find and move the binary
    if [ -f "st" ]; then
        BINARY="st"
    elif [ -f "smart-tree" ]; then
        BINARY="smart-tree"
    else
        echo "${RED}❌ Binary not found in archive${RESET}"
        exit 1
    fi
    
    if [ "$NEED_SUDO" = true ]; then
        sudo mv "$BINARY" "$INSTALL_DIR/st"
        sudo chmod +x "$INSTALL_DIR/st"
    else
        mv "$BINARY" "$INSTALL_DIR/st"
        chmod +x "$INSTALL_DIR/st"
    fi
    
    # Clean up
    cd - >/dev/null
    rm -rf "$TEMP_DIR"
}

# Setup shell integration
setup_shell_integration() {
    echo ""
    echo "${YELLOW}🐚 Setting up shell integration...${RESET}"
    
    # Check if install dir is in PATH
    if ! echo "$PATH" | grep -q "$INSTALL_DIR"; then
        echo "${YELLOW}Adding $INSTALL_DIR to PATH...${RESET}"
        
        # Detect shell and update config
        SHELL_NAME=$(basename "$SHELL")
        case "$SHELL_NAME" in
            bash)
                echo "export PATH=\"$INSTALL_DIR:\$PATH\"" >> "$HOME/.bashrc"
                echo "${GREEN}✓ Updated ~/.bashrc${RESET}"
                ;;
            zsh)
                echo "export PATH=\"$INSTALL_DIR:\$PATH\"" >> "$HOME/.zshrc"
                echo "${GREEN}✓ Updated ~/.zshrc${RESET}"
                ;;
            fish)
                echo "set -gx PATH $INSTALL_DIR \$PATH" >> "$HOME/.config/fish/config.fish"
                echo "${GREEN}✓ Updated fish config${RESET}"
                ;;
            *)
                echo "${YELLOW}⚠️  Add this to your shell config:${RESET}"
                echo "${CYAN}export PATH=\"$INSTALL_DIR:\$PATH\"${RESET}"
                ;;
        esac
    fi
    
    # Setup aliases if requested
    if [ "$INTERACTIVE" = true ]; then
        printf "${YELLOW}Add 'tree' alias for smart-tree? (y/n): ${RESET}"
        read -r response
        if [ "$response" = "y" ] || [ "$response" = "Y" ]; then
            case "$SHELL_NAME" in
                bash)
                    echo "alias tree='st'" >> "$HOME/.bashrc"
                    ;;
                zsh)
                    echo "alias tree='st'" >> "$HOME/.zshrc"
                    ;;
                fish)
                    echo "alias tree='st'" >> "$HOME/.config/fish/config.fish"
                    ;;
            esac
            echo "${GREEN}✓ Added 'tree' alias${RESET}"
        fi
    fi
}

# Main installation flow
main() {
    show_banner
    detect_system
    find_existing_st
    select_install_dir
    install_smart_tree
    setup_mcp
    setup_shell_integration
    
    echo ""
    echo "${GREEN}╔══════════════════════════════════════════╗${RESET}"
    echo "${GREEN}║   ✨ Installation Complete! ✨           ║${RESET}"
    echo "${GREEN}╚══════════════════════════════════════════╝${RESET}"
    echo ""
    echo "${CYAN}smart-tree has been installed to: ${BOLD}$INSTALL_DIR/st${RESET}"
    echo ""
    echo "${YELLOW}Quick start:${RESET}"
    echo "  ${CYAN}st${RESET}              - Show current directory tree"
    echo "  ${CYAN}st --help${RESET}       - Show all options"
    echo "  ${CYAN}st -c${RESET}           - Colorized output"
    echo "  ${CYAN}st -s${RESET}           - Show file sizes"
    echo "  ${CYAN}st --git${RESET}        - Show git status"
    echo ""
    
    if [ ! -z "$ST_PATH" ]; then
        echo "${GREEN}Previous installation has been updated.${RESET}"
    fi
    
    if ! echo "$PATH" | grep -q "$INSTALL_DIR"; then
        echo "${YELLOW}⚠️  Restart your shell or run:${RESET}"
        echo "${CYAN}  source ~/.${SHELL_NAME}rc${RESET}"
    fi
    
    echo ""
    echo "${PURPLE}Made with 💜 by 8b-is${RESET}"
}

# Run main installation
main
INSTALLER_SCRIPT
fi