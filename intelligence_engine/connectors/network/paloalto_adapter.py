import logging

class PaloAltoAdapter:
    def __init__(self, panorama_client):
        self.client = panorama_client
        self.logger = logging.getLogger(__name__)

    def extract_flow_logs(self, query, time_range):
        """
        Extracts traffic flow logs from Palo Alto Networks (Panorama or Cortex Data Lake).
        """
        self.logger.info("Extracting Palo Alto flow logs...")
        raw_logs = self.client.query_traffic_logs(query, time_range)
        return self._normalize_flows(raw_logs)
        
    def _normalize_flows(self, logs):
        flow_logs = []
        for log in logs:
            flow_logs.append({
                'source_ip': log.get('src'),
                'destination_ip': log.get('dst'),
                'source_port': log.get('sport'),
                'destination_port': log.get('dport'),
                'protocol': log.get('proto'),
                'application': log.get('app'),
                'bytes_sent': log.get('bytes_sent'),
                'bytes_received': log.get('bytes_received'),
                'action': log.get('action')
            })
        return flow_logs
