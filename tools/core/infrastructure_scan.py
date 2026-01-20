import os
import json
import hashlib
import time
import shutil
import re
from datetime import datetime
from pathlib import Path

# Add project root to path to allow imports from tools
import sys
project_root = Path(__file__).resolve().parents[2]
sys.path.append(str(project_root))

from tools.discovery.proxmox_api import ProxmoxConnector

# Constants
INFRASTRUCTURE_DIR = project_root / "infrastructure"
STATE_FILE = INFRASTRUCTURE_DIR / "state.json"
CHECKSUM_FILE = INFRASTRUCTURE_DIR / "state.json.checksum"
TEMP_STATE_FILE = INFRASTRUCTURE_DIR / "state.json.tmp"
STATE_HISTORY_DIR = INFRASTRUCTURE_DIR / "state_history"

# Default Providers Configuration (Source of Truth for connection details)
# In V4 this could be discovered via network scan or config file
DEFAULT_PROVIDERS = {
    "ollama": {
        "id": "ollama", 
        "name": "GPU Locale (RTX)", 
        "url": "http://192.168.1.139:11434/v1", 
        "model": "qwen2.5:14b-instruct-q6_K", 
        "type": "openai"
    },
    "qwen_cloud": {
        "id": "qwen_cloud", 
        "name": "Alibaba Qwen Max", 
        "url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", 
        "model": "qwen-max", 
        "type": "openai"
    },
    "gemini-flash": {
        "id": "gemini-flash", 
        "name": "Gemini 2.5 Flash", 
        "model": "gemini-2.0-flash", 
        "type": "google"
    },
    "groq": {
        "id": "groq", 
        "name": "Groq (Llama 3.3)", 
        "url": "https://api.groq.com/openai/v1", 
        "model": "llama-3.3-70b-versatile", 
        "type": "openai"
    }
}

def ensure_infrastructure_dir():
    """Ensure the infrastructure and history directories exist."""
    INFRASTRUCTURE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_HISTORY_DIR.mkdir(parents=True, exist_ok=True)

def calculate_checksum(data_str):
    """Calculate SHA256 checksum of the string content."""
    return hashlib.sha256(data_str.encode('utf-8')).hexdigest()

def scan_infrastructure():
    print("Starting Infrastructure Scan...")
    start_time = time.time()
    
    try:
        connector = ProxmoxConnector()
        nodes = connector.get_nodes()
        
        all_vms = []
        all_lxcs = []
        
        for node in nodes:
            node_name = node['node']
            print(f"Scanning node: {node_name}")
            
            # Fetch VMs
            vms = connector.get_vms(node_name)
            for vm in vms:
                vm['node'] = node_name  # Enrich with node name
                
                # Enrich with IP addresses using QEMU Guest Agent
                try:
                    ips = connector.get_vm_ip(node_name, vm['vmid'])
                    if ips:
                        vm['ip_addresses'] = ips
                    else:
                        vm['ip_addresses'] = []
                except Exception:
                    vm['ip_addresses'] = []
                    
                all_vms.append(vm)
                
            # Fetch Containers
            lxcs = connector.get_containers(node_name)
            for lxc in lxcs:
                lxc['node'] = node_name # Enrich with node name
                all_lxcs.append(lxc)

        end_time = time.time()
        duration_ms = int((end_time - start_time) * 1000)

        # Structure based on Blueprint Section 3.1
        current_iso_time = datetime.now().isoformat()
        
        # Scan Projects (structured)
        projects_dir = project_root.parents[0]
        project_list = scan_projects_structured(projects_dir)

        state_data = {
            "meta": {
                "generated_at": current_iso_time,
                "generated_by": "infrastructure_scan.py",
                "checksum_validation": "See state.json.checksum", # Pointer to external checksum file as per Sec 3.2
                "scan_duration_ms": duration_ms
            },
            "infrastructure": {
                "nodes": nodes,
                "vms": all_vms,
                "lxcs": all_lxcs,
                # Placeholders for future tasks (endpoints, health)
                "endpoints": {}, 
                "health_checks": {} 
            },
            "projects": project_list,
            "api_providers": DEFAULT_PROVIDERS,
            "alerts": [
                # Placeholder as per Sec 3.1
            ]
        }

        # Serialization
        json_output = json.dumps(state_data, indent=2)
        checksum = calculate_checksum(json_output)

        ensure_infrastructure_dir()

        # Atomic Write Sequence (Blueprint Sec 3.2)
        # 1. Write temp file
        print(f"Writing temp file: {TEMP_STATE_FILE}")
        with open(TEMP_STATE_FILE, 'w') as f:
            f.write(json_output)
        
        # 2. Write checksum file
        print(f"Writing checksum: {CHECKSUM_FILE}")
        with open(CHECKSUM_FILE, 'w') as f:
            f.write(checksum)
            
        # 3. Atomic Rename (shutil.move simulates atomic rename or specific os.rename)
        print(f"Finalizing state file: {STATE_FILE}")
        print(f"Finalizing state file: {STATE_FILE}")
        shutil.move(TEMP_STATE_FILE, STATE_FILE)
        
        # 5. Snapshot History (Blueprint Sec 3.3)
        snapshot_filename = f"state_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json"
        snapshot_path = STATE_HISTORY_DIR / snapshot_filename
        print(f"Creating snapshot: {snapshot_path}")
        shutil.copy2(STATE_FILE, snapshot_path)
        
        # 6. Retention Policy (Keep last 50)
        snapshots = sorted(STATE_HISTORY_DIR.glob("state_*.json"), key=os.path.getmtime)
        if len(snapshots) > 50:
            for old_snap in snapshots[:-50]:
                print(f"Retention: Deleting old snapshot {old_snap}")
                old_snap.unlink()
        
        # 7. Generate Global Context
        generate_global_context(state_data)
        
        print(f"Scan completed successfully. Duration: {duration_ms}ms. Checksum: {checksum}")

    except Exception as e:
        print(f"Error during infrastructure scan: {e}")
        # In a real scenario, we might want to log this to an 'alerts' file or similar
        raise

def scan_projects_structured(projects_dir: Path):
    """
    Scans for project_manifest.md files and parses them into a list of dicts.
    """
    print(f"Scanning for project manifests in: {projects_dir}")
    project_list = []
    
    if not projects_dir.exists():
        print(f"Projects directory not found: {projects_dir}")
        return project_list

    for project_path in projects_dir.iterdir():
        if project_path.is_dir():
            manifest_path = project_path / "project_manifest.md"
            if manifest_path.exists():
                print(f"Parsing manifest: {manifest_path}")
                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                        # Regex Parsing
                        name_match = re.search(r'# PROGETTO:\s*(.*)', content)
                        path_match = re.search(r'\*\*Path:\*\*\s*[`\'"]?(.*?)[`\'"]?\s*$', content, re.MULTILINE)
                        status_match = re.search(r'\*\*Stato:\*\*\s*(.*)', content)
                        scope_match = re.search(r'## 🎯 Scopo\s*\n(.*?)\n##', content, re.DOTALL)
                        port_match = re.search(r'\*\*Porta:\*\*\s*(\d+)', content)
                        url_match = re.search(r'\*\*Base URL:\*\*\s*[`\'"]?(.*?)[`\'"]?\s*$', content, re.MULTILINE)

                        project_data = {
                            "id": project_path.name,
                            "name": name_match.group(1).strip() if name_match else project_path.name,
                            "path": path_match.group(1).strip() if path_match else str(project_path),
                            "status": status_match.group(1).strip() if status_match else "Unknown",
                            "description": scope_match.group(1).strip() if scope_match else "",
                            "interfaces": {
                                "port": int(port_match.group(1)) if port_match else None,
                                "base_url": url_match.group(1).strip() if url_match else None
                            },
                            "raw_manifest": content # Keep raw content for GLOBAL_CONTEXT
                        }
                        project_list.append(project_data)
                        
                except Exception as e:
                    print(f"Error parsing manifest {manifest_path}: {e}")
    
    return project_list

def scan_projects(projects_dir: Path):
    """
    Legacy wrapper for scan_projects_structured to return string format.
    NOT USED anymore in main generation logic but kept if needed.
    """
    projects = scan_projects_structured(projects_dir)
    return generate_projects_markdown(projects)

def generate_projects_markdown(projects):
    combined_manifests = "\n# Project Manifests\n\n"
    for p in projects:
        combined_manifests += f"## Project: {p['name']}\n\n"
        combined_manifests += p.get('raw_manifest', '') + "\n\n---\n\n"
    return combined_manifests

def generate_global_context(state_data):
    """
    Generates GLOBAL_CONTEXT.md combining infrastructure state and project manifests.
    """
    print("Generating GLOBAL_CONTEXT.md...")
    projects_dir = project_root.parents[0] # Assuming z:/home/s3ph1r/Projects/neural-home-repo -> Projects is up one level from repo root which is up 2 from script
    # Wait, project_root is .../neural-home-repo.
    # Script is tools/core/infra... (2 levels down from root)
    # project_root definition: Path(__file__).resolve().parents[2] -> neural-home-repo
    # Projects dir is parent of neural-home-repo.
    
    # 1. Infrastructure Summary
    infra_summary = "# GLOBAL CONTEXT & INFRASTRUCTURE HEALTH\n\n"
    infra_summary += f"**Generated At:** {state_data['meta']['generated_at']}\n\n"
    
    infra_summary += "## Infrastructure Status\n\n"
    
    # Nodes
    if 'infrastructure' in state_data and 'nodes' in state_data['infrastructure']:
        for node in state_data['infrastructure']['nodes']:
            cpu_percent = node.get('cpu', 0) * 100
            mem_used_gb = node.get('mem', 0) / (1024**3)
            mem_total_gb = node.get('maxmem', 0) / (1024**3)
            infra_summary += f"- **Node: {node.get('node', 'unknown')}** | Status: {node.get('status', 'unknown')} | CPU: {cpu_percent:.1f}% | RAM: {mem_used_gb:.1f}/{mem_total_gb:.1f} GB\n"
    
    infra_summary += "\n### Active VMs\n\n"
    if 'infrastructure' in state_data and 'vms' in state_data['infrastructure']:
        for vm in state_data['infrastructure']['vms']:
            if vm.get('status') == 'running':
                name = vm.get('name', 'unknown')
                ips = ", ".join(vm.get('ip_addresses', []))
                infra_summary += f"- **{name}** (ID: {vm.get('vmid')}) | IP: {ips}\n"

    infra_summary += "\n---\n"

    # 2. Scan Projects
    # We already have scanned projects in state_data['projects']? 
    # No, generate_global_context is called WITH state_data.
    
    if 'projects' in state_data:
        project_context = generate_projects_markdown(state_data['projects'])
    else:
        # Fallback if state_data doesn't have projects (shouldn't happen with new logic)
        project_context = scan_projects(projects_dir)
    
    # 3. Combine and Write
    full_content = infra_summary + project_context
    
    global_context_path = projects_dir / "GLOBAL_CONTEXT.md"
    try:
        with open(global_context_path, 'w', encoding='utf-8') as f:
            f.write(full_content)
        print(f"Successfully wrote GLOBAL_CONTEXT.md to {global_context_path}")
    except Exception as e:
        print(f"Error writing GLOBAL_CONTEXT.md: {e}")

# Modify scan_infrastructure to call generate_global_context
# We need to insert the call before the end of the function.
# Re-declaring scan_infrastructure to include the call.


if __name__ == "__main__":
    scan_infrastructure()
