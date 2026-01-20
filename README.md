# Neural-Home Infrastructure (NHI)

![Status](https://img.shields.io/badge/Status-Active-green)
![Version](https://img.shields.io/badge/Version-3.0-blue)

**Neural-Home** is a self-aware, distributed AI infrastructure designed to run locally on heterogeneous hardware (Gaming PC + Low-power Server). It leverages a "Single Source of Truth" architecture to allow multiple autonomous AI agents (Aider, Open Interpreter, Antigravity) to collaborate safely.

## 🧠 Core Architecture (v3.0)

### 1. Single Source of Truth
The entire infrastructure state is maintained in `infrastructure/state.json`. 
- **Dynamic**: Updated every minute by `infrastructure_scan.py`.
- **Comprehensive**: Contains real-time data on Proxmox Nodes, VMs, LXC Containers, and **Active Projects**.
- **Safe**: Uses checksum locking (`state.json.checksum`) to prevent read/write race conditions.
- **History**: Snapshots are saved to `infrastructure/state_history/` for debugging and rollback.

### 2. AI Orchestrator
A unified gateway (`orchestrator/`) that intelligently routes AI requests:
- **Local Fallback**: Uses local GPU (Ollama/Qwen) when available to save costs.
- **Cloud Bursting**: Routes to Gemini/Qwen Cloud when local resources are busy (e.g., Gaming PC in use).
- **Project Awareness**: Automatically discovers services via `project_manifest.md` files.

### 3. Automation Tools
Located in `tools/`:
- **`automation/manage_proxmox.py`**: Safe CLI for creating/destroying VMs. Includes protection for Critical VMs (Brain, DB) and Dry-Run mode.
- **`core/infrastructure_scan.py`**: The heartbeat script that updates the state.

## 📂 Repository Structure

```
neural-home-repo/
├── docs/               # Architecture Blueprints
├── infrastructure/     # State files and Dependency Graphs
│   ├── state.json      # LIVE System State
│   ├── dependency_graph.json # Static Service Dependencies
│   └── state_history/  # Historical Snapshots
├── orchestrator/       # AI API Gateway (FastAPI + Redis)
├── tools/              # Automation Scripts
│   ├── automation/     # Action tools (manage_proxmox.py)
│   ├── core/           # Sensing tools (infrastructure_scan.py)
│   └── discovery/      # API wrappers (proxmox_api.py)
└── requirements.txt    # Python Dependencies
```

## 🚀 Getting Started

### Prerequisites
- **Proxmox VE** (8.x+)
- **Python 3.10+**
- **SSH Access** to the remote host (e.g., `192.168.1.20`)

### Installation
All commands should be run on the **Remote Host** (via SSH).

1. **Clone & Setup**
   ```bash
   git clone <repo-url>
   cd neural-home-repo
   python3 -m venv venv
   ./venv/bin/pip install -r requirements.txt
   ```

2. **Configure Secrets**
   Create a `.env` file in the root:
   ```ini
   PROXMOX_HOST=192.168.1.20
   PROXMOX_USER=root@pam
   PROXMOX_TOKEN_ID=...
   PROXMOX_SECRET_KEY=...
   GROQ_API_KEY=...
   GOOGLE_API_KEY=...
   ```

3. **Run the Scanner** (Initialize State)
   ```bash
   ./venv/bin/python tools/core/infrastructure_scan.py
   ```

4. **Start Orchestrator**
   ```bash
   ./venv/bin/uvicorn orchestrator.main:app --host 0.0.0.0 --port 8000
   ```

## 🛡️ Safety Protocols
- **Critical IO**: Agents are forbidden from modifying `state.json` manually. They must use the tools.
- **Dependency Awareness**: Before stopping a service, agents must check `infrastructure/dependency_graph.json`.
