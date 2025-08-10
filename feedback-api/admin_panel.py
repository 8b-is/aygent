#!/usr/bin/env python3
"""
Admin Panel for Smart-Tree Feedback System
Beautiful web interface for managing feedback, agents, and monitoring
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import hashlib
from collections import defaultdict

from auth import verify_token, check_permission, verify_admin, create_access_token, AGENT_KEYS, AdminLogin
from llm_assistant import get_assistant, SmartTreeTask

router = APIRouter(prefix="/admin", tags=["admin"])

# Admin panel HTML template
ADMIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Smart-Tree Admin Panel | 8b-is</title>
    <style>
        :root {
            --primary: #00ff88;
            --secondary: #8b00ff;
            --danger: #ff4444;
            --warning: #ffaa00;
            --bg-dark: #0a0a0a;
            --bg-darker: #050505;
            --bg-card: #1a1a1a;
            --text: #e0e0e0;
            --text-dim: #999;
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
        }
        
        .header {
            background: var(--bg-card);
            border-bottom: 2px solid var(--primary);
            padding: 1.5rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .header h1 {
            background: linear-gradient(90deg, var(--primary) 0%, var(--secondary) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 2rem;
        }
        
        .nav {
            display: flex;
            gap: 2rem;
            background: var(--bg-card);
            padding: 1rem 2rem;
            border-bottom: 1px solid var(--border);
        }
        
        .nav-item {
            color: var(--text-dim);
            text-decoration: none;
            padding: 0.5rem 1rem;
            border-radius: 4px;
            transition: all 0.3s;
        }
        
        .nav-item:hover, .nav-item.active {
            color: var(--primary);
            background: rgba(0, 255, 136, 0.1);
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        
        .stat-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1.5rem;
            transition: transform 0.3s;
        }
        
        .stat-card:hover {
            transform: translateY(-5px);
            border-color: var(--primary);
        }
        
        .stat-value {
            font-size: 2.5rem;
            font-weight: bold;
            color: var(--primary);
        }
        
        .stat-label {
            color: var(--text-dim);
            margin-top: 0.5rem;
        }
        
        .section {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 2rem;
            margin-bottom: 2rem;
        }
        
        .section h2 {
            color: var(--secondary);
            margin-bottom: 1.5rem;
            display: flex;
            align-items: center;
            gap: 1rem;
        }
        
        .table {
            width: 100%;
            border-collapse: collapse;
        }
        
        .table th {
            background: rgba(139, 0, 255, 0.1);
            color: var(--secondary);
            padding: 1rem;
            text-align: left;
            border-bottom: 2px solid var(--secondary);
        }
        
        .table td {
            padding: 1rem;
            border-bottom: 1px solid var(--border);
        }
        
        .table tr:hover {
            background: rgba(0, 255, 136, 0.05);
        }
        
        .badge {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 12px;
            font-size: 0.85rem;
            font-weight: bold;
        }
        
        .badge-success {
            background: rgba(0, 255, 136, 0.2);
            color: var(--primary);
        }
        
        .badge-warning {
            background: rgba(255, 170, 0, 0.2);
            color: var(--warning);
        }
        
        .badge-danger {
            background: rgba(255, 68, 68, 0.2);
            color: var(--danger);
        }
        
        .btn {
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            color: var(--bg-darker);
            border: none;
            padding: 0.75rem 1.5rem;
            border-radius: 6px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .btn:hover {
            transform: scale(1.05);
            box-shadow: 0 5px 20px rgba(139, 0, 255, 0.4);
        }
        
        .btn-danger {
            background: linear-gradient(135deg, var(--danger) 0%, #cc0000 100%);
        }
        
        .agent-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 1rem;
        }
        
        .agent-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }
        
        .agent-name {
            font-size: 1.2rem;
            color: var(--primary);
        }
        
        .permissions {
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
            margin-top: 0.5rem;
        }
        
        .permission-tag {
            background: rgba(139, 0, 255, 0.1);
            color: var(--secondary);
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.85rem;
        }
        
        .chart-container {
            height: 300px;
            margin-top: 1rem;
        }
        
        .login-container {
            max-width: 400px;
            margin: 10rem auto;
            background: var(--bg-card);
            border: 2px solid var(--primary);
            border-radius: 12px;
            padding: 2rem;
        }
        
        .login-container h2 {
            color: var(--primary);
            margin-bottom: 2rem;
            text-align: center;
        }
        
        .form-group {
            margin-bottom: 1.5rem;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 0.5rem;
            color: var(--text-dim);
        }
        
        .form-group input {
            width: 100%;
            padding: 0.75rem;
            background: var(--bg-darker);
            border: 1px solid var(--border);
            border-radius: 4px;
            color: var(--text);
            font-family: inherit;
        }
        
        .form-group input:focus {
            outline: none;
            border-color: var(--primary);
        }
        
        .alert {
            padding: 1rem;
            border-radius: 6px;
            margin-bottom: 1rem;
        }
        
        .alert-danger {
            background: rgba(255, 68, 68, 0.1);
            border: 1px solid var(--danger);
            color: var(--danger);
        }
        
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid var(--border);
            border-top-color: var(--primary);
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div id="app">
        <div v-if="!authenticated" class="login-container">
            <h2>🔐 Admin Login</h2>
            <div v-if="error" class="alert alert-danger">{{ error }}</div>
            <div class="form-group">
                <label>Username</label>
                <input v-model="username" type="text" placeholder="Enter username">
            </div>
            <div class="form-group">
                <label>Password</label>
                <input v-model="password" type="password" placeholder="Enter password" @keyup.enter="login">
            </div>
            <button class="btn" @click="login" style="width: 100%">Login</button>
        </div>
        
        <div v-else>
            <div class="header">
                <h1>🌲 Smart-Tree Admin Panel</h1>
                <div>
                    <span style="margin-right: 1rem;">Welcome, {{ currentUser }}</span>
                    <button class="btn btn-danger" @click="logout">Logout</button>
                </div>
            </div>
            
            <nav class="nav">
                <a href="#" class="nav-item" :class="{active: currentTab === 'dashboard'}" @click="currentTab = 'dashboard'">Dashboard</a>
                <a href="#" class="nav-item" :class="{active: currentTab === 'feedback'}" @click="currentTab = 'feedback'">Feedback</a>
                <a href="#" class="nav-item" :class="{active: currentTab === 'agents'}" @click="currentTab = 'agents'">Agents</a>
                <a href="#" class="nav-item" :class="{active: currentTab === 'llm'}" @click="currentTab = 'llm'">LLM Assistant</a>
                <a href="#" class="nav-item" :class="{active: currentTab === 'monitoring'}" @click="currentTab = 'monitoring'">Monitoring</a>
            </nav>
            
            <div class="container">
                <!-- Dashboard Tab -->
                <div v-if="currentTab === 'dashboard'">
                    <div class="stats-grid">
                        <div class="stat-card">
                            <div class="stat-value">{{ stats.total_feedback }}</div>
                            <div class="stat-label">Total Feedback</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">{{ stats.active_agents }}</div>
                            <div class="stat-label">Active Agents</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">{{ stats.requests_today }}</div>
                            <div class="stat-label">Requests Today</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">{{ stats.llm_calls }}</div>
                            <div class="stat-label">LLM Calls</div>
                        </div>
                    </div>
                    
                    <div class="section">
                        <h2>📊 Recent Activity</h2>
                        <div class="chart-container">
                            <!-- Chart would go here -->
                            <canvas id="activityChart"></canvas>
                        </div>
                    </div>
                </div>
                
                <!-- Feedback Tab -->
                <div v-if="currentTab === 'feedback'" class="section">
                    <h2>📝 Feedback Management</h2>
                    <table class="table">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Category</th>
                                <th>Title</th>
                                <th>Model</th>
                                <th>Impact</th>
                                <th>Status</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr v-for="item in feedbackItems">
                                <td>{{ item.id.substring(0, 8) }}</td>
                                <td><span class="badge" :class="getCategoryClass(item.category)">{{ item.category }}</span></td>
                                <td>{{ item.title }}</td>
                                <td>{{ item.ai_model }}</td>
                                <td>{{ item.impact_score }}/10</td>
                                <td><span class="badge badge-warning">Pending</span></td>
                                <td>
                                    <button class="btn" style="padding: 0.5rem 1rem;">Process</button>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                
                <!-- Agents Tab -->
                <div v-if="currentTab === 'agents'">
                    <div class="section">
                        <h2>🤖 Agent Management</h2>
                        <div v-for="agent in agents" class="agent-card">
                            <div class="agent-header">
                                <div>
                                    <div class="agent-name">{{ agent.name }}</div>
                                    <div style="color: var(--text-dim); margin-top: 0.5rem;">
                                        ID: {{ agent.id }} | Rate Limit: {{ agent.rate_limit }}/min
                                    </div>
                                </div>
                                <div>
                                    <span class="badge badge-success">Active</span>
                                </div>
                            </div>
                            <div class="permissions">
                                <span v-for="perm in agent.permissions" class="permission-tag">{{ perm }}</span>
                            </div>
                            <div style="margin-top: 1rem;">
                                <small style="color: var(--text-dim);">API Key: {{ agent.api_key_preview }}...</small>
                            </div>
                        </div>
                        <button class="btn" style="margin-top: 1rem;">+ Add New Agent</button>
                    </div>
                </div>
                
                <!-- LLM Tab -->
                <div v-if="currentTab === 'llm'" class="section">
                    <h2>🧠 LLM Assistant Configuration</h2>
                    <div style="margin-bottom: 2rem;">
                        <h3 style="color: var(--primary); margin-bottom: 1rem;">OpenRouter Settings</h3>
                        <div class="form-group">
                            <label>API Key</label>
                            <input type="password" value="sk_or_***********" style="max-width: 400px;">
                        </div>
                        <div class="form-group">
                            <label>Default Model</label>
                            <select style="padding: 0.75rem; background: var(--bg-darker); border: 1px solid var(--border); color: var(--text); max-width: 400px;">
                                <option>anthropic/claude-3-haiku</option>
                                <option>anthropic/claude-3-sonnet</option>
                                <option>meta-llama/llama-3.1-8b-instruct</option>
                                <option>mistralai/mistral-7b-instruct</option>
                            </select>
                        </div>
                    </div>
                    
                    <h3 style="color: var(--primary); margin-bottom: 1rem;">Recent LLM Tasks</h3>
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Task Type</th>
                                <th>Model</th>
                                <th>Tokens</th>
                                <th>Cost</th>
                                <th>Cached</th>
                                <th>Time</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr v-for="task in llmTasks">
                                <td>{{ task.task_type }}</td>
                                <td>{{ task.model }}</td>
                                <td>{{ task.tokens }}</td>
                                <td>${{ task.cost.toFixed(4) }}</td>
                                <td><span class="badge" :class="task.cached ? 'badge-success' : ''">{{ task.cached ? 'Yes' : 'No' }}</span></td>
                                <td>{{ formatTime(task.timestamp) }}</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                
                <!-- Monitoring Tab -->
                <div v-if="currentTab === 'monitoring'" class="section">
                    <h2>📈 System Monitoring</h2>
                    <div class="stats-grid">
                        <div class="stat-card">
                            <div class="stat-value">{{ monitoring.uptime }}</div>
                            <div class="stat-label">Uptime</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">{{ monitoring.requests_per_minute }}</div>
                            <div class="stat-label">Requests/min</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">{{ monitoring.avg_response_time }}ms</div>
                            <div class="stat-label">Avg Response Time</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">{{ monitoring.error_rate }}%</div>
                            <div class="stat-label">Error Rate</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/vue@3/dist/vue.global.prod.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        const { createApp } = Vue;
        
        createApp({
            data() {
                return {
                    authenticated: false,
                    currentUser: '',
                    username: '',
                    password: '',
                    error: '',
                    currentTab: 'dashboard',
                    stats: {
                        total_feedback: 0,
                        active_agents: 0,
                        requests_today: 0,
                        llm_calls: 0
                    },
                    feedbackItems: [],
                    agents: [],
                    llmTasks: [],
                    monitoring: {
                        uptime: '0d 0h',
                        requests_per_minute: 0,
                        avg_response_time: 0,
                        error_rate: 0
                    }
                };
            },
            methods: {
                async login() {
                    try {
                        const response = await fetch('/admin/api/login', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({
                                username: this.username,
                                password: this.password
                            })
                        });
                        
                        if (response.ok) {
                            const data = await response.json();
                            localStorage.setItem('admin_token', data.access_token);
                            this.authenticated = true;
                            this.currentUser = this.username;
                            this.loadData();
                        } else {
                            this.error = 'Invalid credentials';
                        }
                    } catch (err) {
                        this.error = 'Login failed';
                    }
                },
                logout() {
                    localStorage.removeItem('admin_token');
                    this.authenticated = false;
                    this.username = '';
                    this.password = '';
                },
                async loadData() {
                    const token = localStorage.getItem('admin_token');
                    const headers = {'Authorization': `Bearer ${token}`};
                    
                    // Load stats
                    const statsResponse = await fetch('/admin/api/stats', {headers});
                    this.stats = await statsResponse.json();
                    
                    // Load feedback
                    const feedbackResponse = await fetch('/admin/api/feedback', {headers});
                    this.feedbackItems = await feedbackResponse.json();
                    
                    // Load agents
                    const agentsResponse = await fetch('/admin/api/agents', {headers});
                    this.agents = await agentsResponse.json();
                    
                    // Load LLM tasks
                    const llmResponse = await fetch('/admin/api/llm/tasks', {headers});
                    this.llmTasks = await llmResponse.json();
                    
                    // Load monitoring
                    const monitoringResponse = await fetch('/admin/api/monitoring', {headers});
                    this.monitoring = await monitoringResponse.json();
                },
                getCategoryClass(category) {
                    const classes = {
                        'bug': 'badge-danger',
                        'critical': 'badge-danger',
                        'nice_to_have': 'badge-success',
                        'tool_request': 'badge-warning'
                    };
                    return classes[category] || '';
                },
                formatTime(timestamp) {
                    return new Date(timestamp).toLocaleString();
                }
            },
            mounted() {
                // Check for existing token
                const token = localStorage.getItem('admin_token');
                if (token) {
                    // Verify token is still valid
                    fetch('/admin/api/verify', {
                        headers: {'Authorization': `Bearer ${token}`}
                    }).then(response => {
                        if (response.ok) {
                            this.authenticated = true;
                            this.loadData();
                        }
                    });
                }
            }
        }).mount('#app');
    </script>
</body>
</html>
"""


@router.get("/", response_class=HTMLResponse)
async def admin_panel():
    """Serve the admin panel HTML"""
    return ADMIN_HTML


@router.post("/api/login")
async def admin_login(credentials: AdminLogin):
    """Admin login endpoint"""
    if not verify_admin(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Create admin token
    admin_data = {
        "name": f"Admin ({credentials.username})",
        "permissions": ["*"],
        "rate_limit": 1000,
    }
    
    token = create_access_token(f"admin_{credentials.username}", admin_data)
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 86400,
    }


@router.get("/api/verify")
async def verify_admin_token(token_data: Dict = Depends(verify_token)):
    """Verify admin token is valid"""
    return {"valid": True, "user": token_data.get("name")}


@router.get("/api/stats")
async def get_admin_stats(admin: Dict = Depends(check_permission("admin.read"))):
    """Get dashboard statistics"""
    # These would come from database in production
    return {
        "total_feedback": 156,
        "active_agents": len(AGENT_KEYS),
        "requests_today": 423,
        "llm_calls": 89,
    }


@router.get("/api/feedback")
async def get_feedback_items(
    admin: Dict = Depends(check_permission("admin.read")),
    limit: int = 20
):
    """Get recent feedback items"""
    # Read from feedback directory
    feedback_items = []
    feedback_dir = Path("./feedback")
    
    if feedback_dir.exists():
        for date_dir in sorted(feedback_dir.iterdir(), reverse=True):
            if date_dir.is_dir():
                for summary_file in date_dir.glob("*.summary.txt"):
                    try:
                        with open(summary_file, "r") as f:
                            content = f.read()
                            
                            # Parse summary
                            item = {"id": summary_file.stem.replace(".summary", "")}
                            for line in content.split("\n"):
                                if line.startswith("Category:"):
                                    item["category"] = line.split(":", 1)[1].strip()
                                elif line.startswith("Title:"):
                                    item["title"] = line.split(":", 1)[1].strip()
                                elif line.startswith("Model:"):
                                    item["ai_model"] = line.split(":", 1)[1].strip()
                                elif line.startswith("Impact:"):
                                    try:
                                        item["impact_score"] = int(line.split(":")[1].split("/")[0].strip())
                                    except:
                                        item["impact_score"] = 5
                            
                            feedback_items.append(item)
                            
                            if len(feedback_items) >= limit:
                                return feedback_items
                    except Exception as e:
                        continue
    
    return feedback_items


@router.get("/api/agents")
async def get_agents_list(admin: Dict = Depends(check_permission("admin.read"))):
    """Get list of configured agents"""
    agents = []
    for agent_id, agent_data in AGENT_KEYS.items():
        agents.append({
            "id": agent_id,
            "name": agent_data["name"],
            "permissions": agent_data["permissions"],
            "rate_limit": agent_data["rate_limit"],
            "api_key_preview": agent_data["secret"][:10] if len(agent_data["secret"]) > 10 else "***",
        })
    return agents


@router.get("/api/llm/tasks")
async def get_llm_tasks(admin: Dict = Depends(check_permission("admin.read"))):
    """Get recent LLM tasks"""
    # Read from cache directory
    tasks = []
    cache_dir = Path("./llm_cache")
    
    if cache_dir.exists():
        for cache_file in sorted(cache_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:10]:
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                    tasks.append({
                        "task_type": "unknown",  # Would be in the data
                        "model": data.get("model_used", "unknown"),
                        "tokens": data.get("tokens_used", 0),
                        "cost": data.get("cost_estimate", 0.0),
                        "cached": data.get("cached", False),
                        "timestamp": data.get("timestamp", ""),
                    })
            except:
                continue
    
    return tasks


@router.get("/api/monitoring")
async def get_monitoring_stats(admin: Dict = Depends(check_permission("admin.read"))):
    """Get system monitoring stats"""
    # Calculate uptime (mock for now)
    import psutil
    import time
    
    boot_time = psutil.boot_time()
    current_time = time.time()
    uptime_seconds = current_time - boot_time
    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    
    return {
        "uptime": f"{days}d {hours}h",
        "requests_per_minute": 42,
        "avg_response_time": 85,
        "error_rate": 0.1,
    }


@router.post("/api/agents")
async def create_agent(
    agent_data: Dict[str, Any],
    admin: Dict = Depends(check_permission("admin.write"))
):
    """Create new agent"""
    # In production, this would save to database
    agent_id = f"agent_{agent_data['name'].lower().replace(' ', '_')}"
    
    AGENT_KEYS[agent_id] = {
        "secret": "sk_" + hashlib.sha256(f"{agent_id}:{datetime.now()}".encode()).hexdigest()[:32],
        "name": agent_data["name"],
        "permissions": agent_data.get("permissions", ["feedback.submit", "feedback.read"]),
        "rate_limit": agent_data.get("rate_limit", 60),
    }
    
    return {"message": "Agent created", "agent_id": agent_id}


@router.delete("/api/agents/{agent_id}")
async def delete_agent(
    agent_id: str,
    admin: Dict = Depends(check_permission("admin.write"))
):
    """Delete an agent"""
    if agent_id in AGENT_KEYS:
        del AGENT_KEYS[agent_id]
        return {"message": "Agent deleted"}
    
    raise HTTPException(status_code=404, detail="Agent not found")


# Export router for main app
__all__ = ["router"]