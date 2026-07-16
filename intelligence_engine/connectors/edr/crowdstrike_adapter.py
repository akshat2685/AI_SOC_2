import logging

class CrowdStrikeAdapter:
    def __init__(self, api_client):
        self.api_client = api_client
        self.logger = logging.getLogger(__name__)

    def extract_process_trees(self, host_id, timeframe):
        """
        Extracts process trees and parent-child chains from CrowdStrike.
        """
        self.logger.info(f"Extracting CrowdStrike process tree for host {host_id}")
        # Mocking API call to CrowdStrike for process events
        raw_events = self.api_client.get_process_events(host_id, timeframe)
        return self._build_process_tree(raw_events)
        
    def _build_process_tree(self, events):
        process_tree = {}
        for event in events:
            pid = event.get('TargetProcessId')
            ppid = event.get('ParentProcessId')
            process_tree[pid] = {
                'ppid': ppid,
                'image_filename': event.get('FileName'),
                'command_line': event.get('CommandLine')
            }
        return process_tree
