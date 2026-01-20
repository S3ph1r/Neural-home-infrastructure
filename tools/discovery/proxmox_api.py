import os
from proxmoxer import ProxmoxAPI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class ProxmoxConnector:
    """
    Connector for Proxmox VE API.
    Reads credentials from environment variables.
    Reference: Neural-Home Infrastructure Blueprint v3.0 - Task 1.1
    """

    def __init__(self):
        self.host = os.getenv("PROXMOX_HOST")
        self.user = os.getenv("PROXMOX_USER")
        self.token_id = os.getenv("PROXMOX_TOKEN_ID")
        self.secret_key = os.getenv("PROXMOX_SECRET_KEY")

        if not all([self.host, self.user, self.token_id, self.secret_key]):
            raise ValueError("Missing Proxmox credentials in .env file.")

        # Initialize ProxmoxAPI
        # verify_ssl=False is required for local self-signed certs (LAN)
        self.proxmox = ProxmoxAPI(
            self.host,
            user=self.user,
            token_name=self.token_id,
            token_value=self.secret_key,
            verify_ssl=False
        )

    def get_nodes(self):
        """Retrieve list of nodes in the cluster."""
        return self.proxmox.nodes.get()

    def get_vms(self, node):
        """Retrieve specific QEMU VMs for a node."""
        return self.proxmox.nodes(node).qemu.get()

    def get_containers(self, node):
        """Retrieve specific LXC containers for a node."""
        return self.proxmox.nodes(node).lxc.get()
    
    def get_resources(self):
        """Retrieve cluster resources (nodes, qemu, lxc, storage)."""
        return self.proxmox.cluster.resources.get()

    def get_vm_ip(self, node, vmid):
        """
        Retrieve IPv4 address for a QEMU VM using Guest Agent.
        Ignores loopback and IPv6.
        """
        try:
            # Call QEMU Guest Agent API
            interfaces = self.proxmox.nodes(node).qemu(vmid).agent('network-get-interfaces').get()
            
            ips = []
            if 'result' in interfaces:
                for iface in interfaces['result']:
                    if iface.get('name') == 'lo':
                        continue
                    
                    for ip_info in iface.get('ip-addresses', []):
                        if ip_info['ip-address-type'] == 'ipv4':
                            ips.append(ip_info['ip-address'])
            
            return ips if ips else None

        except Exception as e:
            # Agent might not be running or installed
            # print(f"Could not get IP for VM {vmid} on node {node}: {e}")
            return None
