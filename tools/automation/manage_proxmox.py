
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
CRITICAL_VMS = [100, 101, 102, 103] # Brain, Chroma, Postgres, Observability
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

    def destroy_vm(self, node, vmid):
        logger.info(f"REQUEST: Destroy VM {vmid} on {node}")
        
        if int(vmid) in CRITICAL_VMS:
            logger.error(f"CRITICAL SAFETY STOP: Attempted to destroy protected VM {vmid}!")
            return False

        if self.dry_run:
            logger.info(f"[DRY-RUN] Would execute: Stop VM {vmid}, Destroy VM {vmid}")
            return True

        try:
            # 1. Stop if running
            try:
                status = self._get_node(node).qemu(vmid).status.current.get()
                if status['status'] == 'running':
                    logger.info("Stopping VM...")
                    self._get_node(node).qemu(vmid).status.stop.post()
                    time.sleep(10) # Wait for shutdown
            except Exception:
                pass # Maybe doesn't exist or already stopped

            # 2. Destroy
            logger.info("Destroying VM...")
            self._get_node(node).qemu(vmid).delete()
            logger.info(f"SUCCESS: VM {vmid} destroyed.")
            return True
        except Exception as e:
            logger.error(f"FAILED: {e}")
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

    # Destroy
    destroy_parser = subparsers.add_parser("destroy", help="Destroy a VM")
    destroy_parser.add_argument("--vmid", required=True, type=int, help="VM ID to destroy")

    args = parser.parse_args()
    
    manager = ProxmoxManager(dry_run=args.dry_run)

    if args.command == "list":
        manager.list_vms(args.node)
    elif args.command == "create":
        manager.create_vm(args.node, args.template_id, args.new_id, args.name, args.cores, args.memory)
    elif args.command == "destroy":
        manager.destroy_vm(args.node, args.vmid)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
