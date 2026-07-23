import structlog

class DefenderAdapter:
    def __init__(self, m365_client):
        self.client = m365_client
        self.logger = structlog.get_logger(__name__)

    def extract_process_chains(self, device_id, time_range):
        """
        Extracts parent-child process chains from Microsoft Defender for Endpoint.
        """
        self.logger.info(f"Extracting Defender process chains for device {device_id}")
        query = f"DeviceProcessEvents | where DeviceId == '{device_id}' | project ProcessId, InitiatingProcessId, FileName, ProcessCommandLine"
        raw_data = self.client.run_advanced_hunting(query, time_range)
        return self._parse_chains(raw_data)
        
    def _parse_chains(self, data):
        chains = []
        for row in data:
            chains.append({
                'process_id': row.get('ProcessId'),
                'parent_process_id': row.get('InitiatingProcessId'),
                'file_name': row.get('FileName'),
                'command_line': row.get('ProcessCommandLine')
            })
        return chains
