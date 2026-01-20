
import argparse
import sys
import logging
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parents[2]
sys.path.append(str(project_root))

from tools.discovery.proxmox_api import ProxmoxConnector

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Safety Configuration
CRITICAL_VMS = [100] # Brain only (others are being built)
SAFE_MODE = True

class ProxmoxManager:
    def __init__(self, dry_run=False):
        self.connector = ProxmoxConnector()
        self.proxmox = self.connector.proxmox
        self.dry_run = dry_run

    def _get_node(self, node_name="homelab"):
        return self.proxmox.nodes(node_name)

    def list_vms(self, node="homelab"):
        vms = self.connector.get_vms(node)
        for vm in vms:
            print(f"[{vm['vmid']}] {vm['name']} - Status: {vm['status']}")

    def create_vm(self, node, template_id, new_id, name, cores=2, memory=2048):
        logger.info(f"REQUEST: Clone Template {template_id} -> New VM {new_id} ({name}) on {node}")
        
        if int(new_id) in CRITICAL_VMS:
            logger.error(f"ABORTING: Cannot overwrite critical VM ID {new_id}")
            return False

        if self.dry_run:
            logger.info("[DRY-RUN] Would execute: Clone template, Set cores={cores}, Set memory={memory}, Start VM")
            returnTrue

        try:
            # 1. Clone
            logger.info("Cloning...")
            self._get_node(node).qemu(template_id).clone.create(newid=new_id, name=name, full=1)
            
            # Wait for clone to finish (simplified, ideally monitor task)
            time.sleep(5) 

            # 2. Config Resources
            logger.info("Configuring resources...")
            self._get_node(node).qemu(new_id).config.set(cores=cores, memory=memory)

            # 3. Start
            logger.info("Starting VM...")
            self._get_node(node).qemu(new_id).status.start.post()
            
            logger.info(f"SUCCESS: VM {name} ({new_id}) created and started.")
            return True
        except Exception as e:
            logger.error(f"FAILED: {e}")
            return False

            logger.error(f"FAILED LXC CREATION: {e}")
            return False

    def destroy_vm(self, node, vmid):
        logger.info(f"REQUEST: Destroy Resource {vmid} on {node}")
        
        if int(vmid) in CRITICAL_VMS:
            logger.error(f"CRITICAL SAFETY STOP: Attempted to destroy protected Resource {vmid}!")
            return False

        if self.dry_run:
            logger.info(f"[DRY-RUN] Would destroy {vmid}")
            return True

        try:
            # Try QEMU first
            try:
                self._get_node(node).qemu(vmid).status.stop.post()
                time.sleep(5)
                self._get_node(node).qemu(vmid).delete()
                logger.info(f"SUCCESS: VM {vmid} destroyed.")
                return True
            except Exception:
                # Try LXC
                try:
                    self._get_node(node).lxc(vmid).status.stop.post()
                    time.sleep(5)
                except: pass
                
                self._get_node(node).lxc(vmid).delete()
                logger.info(f"SUCCESS: LXC {vmid} destroyed.")
                return True
                
        except Exception as e:
            logger.error(f"FAILED DESTROY: {e}")
            return False

    def create_lxc(self, node, vmid, name, ostemplate, cores=2, memory=2048, password="password", ip="dhcp", ssh_key=None):
        logger.info(f"REQUEST: Create LXC {vmid} ({name}) using {ostemplate} IP={ip}")
        
        if int(vmid) in CRITICAL_VMS:
            logger.error(f"ABORTING: Cannot overwrite critical ID {vmid}")
            return False

        if self.dry_run:
            logger.info(f"[DRY-RUN] Would create LXC {vmid} with {ostemplate}")
            return True

        try:
            logger.info("Creating LXC Container...")
            
            # Formatting network string
            net_config = f"name=eth0,bridge=vmbr0,ip={ip}"
            if ip != "dhcp":
                if "/" not in ip:
                   net_config += "/24"
                # Add Gateway (Hardcoded for now based on subnet standard)
                net_config += ",gw=192.168.1.1"
                
            # Basic LXC creation
            params = {
                "vmid": vmid,
                "hostname": name,
                "ostemplate": ostemplate,
                "cores": cores,
                "memory": memory,
                "password": password,
                "rootfs": "local-lvm:10",
                "net0": net_config,
                "features": "nesting=1",
                "start": 1
            }
            
            if ssh_key:
                # Proxmox API expects URL-encoded key usually, but library might handle it.
                # However, the key argument is usually 'ssh-public-keys'
                params["ssh-public-keys"] = ssh_key

            self._get_node(node).lxc.create(**params)
            logger.info(f"SUCCESS: LXC {name} ({vmid}) started.")
            return True
        except Exception as e:
            logger.error(f"FAILED LXC CREATION: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(description="Neural-Home Proxmox Automation Tool")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without execution")
    parser.add_argument("--node", default="homelab", help="Target Proxmox Node")
    
    subparsers = parser.add_subparsers(dest="command")

    # List
    subparsers.add_parser("list", help="List all VMs")

    # Create
    create_parser = subparsers.add_parser("create", help="Create a new VM from template")
    create_parser.add_argument("--template-id", required=True, type=int, help="Source Template ID")
    create_parser.add_argument("--new-id", required=True, type=int, help="New VM ID")
    create_parser.add_argument("--name", required=True, help="New VM Name")
    create_parser.add_argument("--cores", type=int, default=2, help="CPU Cores")
    create_parser.add_argument("--memory", type=int, default=2048, help="RAM in MB")
    create_parser.add_argument("--type", choices=["vm", "lxc"], default="vm", help="Resource Type")
    create_parser.add_argument("--ostemplate", help="OS Template for LXC (e.g., local:vztmpl/ubuntu-22.04.tar.gz)")
    create_parser.add_argument("--ip", default="dhcp", help="IP Address (e.g. 192.168.1.103/24) or 'dhcp'")
    create_parser.add_argument("--password", default="password", help="Root password for LXC")
    create_parser.add_argument("--ssh-key", help="Public SSH Key to inject")

    # Destroy
    destroy_parser = subparsers.add_parser("destroy", help="Destroy a VM")
    destroy_parser.add_argument("--vmid", required=True, type=int, help="VM ID to destroy")

    args = parser.parse_args()
    
    manager = ProxmoxManager(dry_run=args.dry_run)

    if args.command == "list":
        manager.list_vms(args.node)
    elif args.command == "create":
        if args.type == "vm":
            manager.create_vm(args.node, args.template_id, args.new_id, args.name, args.cores, args.memory)
        elif args.type == "lxc":
            if not args.ostemplate:
                print("Error: --ostemplate is required for LXC creation")
            else:
                manager.create_lxc(args.node, args.new_id, args.name, args.ostemplate, args.cores, args.memory, args.password, args.ip, args.ssh_key)
    elif args.command == "destroy":
        manager.destroy_vm(args.node, args.vmid)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
