import json
import os
from pathlib import Path

# Path to state.json
# Assuming this script is in tools/automation/, so state.json is in ../../infrastructure/state.json
PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = PROJECT_ROOT / "infrastructure" / "state.json"

def get_vm_ip(vm_name):
    """
    Reads infrastructure/state.json and finds the IP address of a VM or Container by its name.
    
    Args:
        vm_name (str): The name of the VM or Container (e.g., 'brain-vm', 'postgres-lxc').
        
    Returns:
        str: The IP address if found, None otherwise.
        
    Raises:
        FileNotFoundError: If state.json does not exist.
    """
    if not STATE_FILE.exists():
        print(f"Error: State file not found at {STATE_FILE}. Run infrastructure scan first.")
        return None

    try:
        with open(STATE_FILE, 'r') as f:
            state_data = json.load(f)
            
        infrastructure = state_data.get('infrastructure', {})
        
        # Search in VMs
        for vm in infrastructure.get('vms', []):
            if vm.get('name') == vm_name:
                # Priority 1: New 'ip_addresses' field from QEMU Guest Agent
                if vm.get('ip_addresses'):
                    return vm['ip_addresses'][0] # Return first IP
                
                # Priority 2: 'ip' field (if exists)
                if vm.get('ip'):
                    return vm['ip']
                    
                # Priority 3: Safe check on 'netin' (avoiding AttributeError if it's not a dict)
                netin = vm.get('netin')
                if isinstance(netin, dict):
                    return netin.get('ip')
                
                return None

        # Search in LXCs
        for lxc in infrastructure.get('lxcs', []):
            if lxc.get('name') == vm_name:
                # LXC objects usually have 'net0' like "name=eth0,bridge=vmbr0,firewall=1,gw=...,hwaddr=...,ip=192.168.1.102/24,type=veth"
                net_config = lxc.get('net0', '')
                if 'ip=' in net_config:
                    # Extract IP simple parse
                    parts = net_config.split(',')
                    for part in parts:
                        if part.strip().startswith('ip='):
                            return part.split('=')[1].split('/')[0] # Remove CIDR
                return None

        print(f"VM/Container '{vm_name}' not found in state.")
        return None

    except json.JSONDecodeError:
        print(f"Error: Failed to decode {STATE_FILE}.")
        return None
    except Exception as e:
        print(f"Error reading state file: {e}")
        return None

if __name__ == "__main__":
    # Test
    import sys
    if len(sys.argv) > 1:
        target = sys.argv[1]
        ip = get_vm_ip(target)
        if ip:
            print(f"IP for {target}: {ip}")
        else:
            print(f"Could not resolve IP for {target}")
