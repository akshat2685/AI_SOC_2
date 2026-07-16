from ...core.observability import trace

class FirewallConnector:
    @trace("firewall_block_ip")
    def block_ip(self, ip_address: str) -> dict:
        """Blocks an IP address on the firewall."""
        return {"status": "success", "action": "block_ip", "ip": ip_address}
        
    @trace("firewall_unblock_ip")
    def unblock_ip(self, ip_address: str) -> dict:
        """Unblocks an IP address on the firewall."""
        return {"status": "success", "action": "unblock_ip", "ip": ip_address}
