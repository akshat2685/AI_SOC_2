import logging

class ZeekAdapter:
    def __init__(self, log_reader):
        self.log_reader = log_reader
        self.logger = logging.getLogger(__name__)

    def extract_flow_logs(self, filter_params):
        """
        Extracts network flow logs from Zeek conn.log.
        """
        self.logger.info("Extracting Zeek flow logs from conn.log")
        conn_logs = self.log_reader.read_log('conn')
        return self._process_conn_logs(conn_logs, filter_params)
        
    def _process_conn_logs(self, logs, filter_params):
        processed_flows = []
        for flow in logs:
            processed_flows.append({
                'ts': flow.get('ts'),
                'uid': flow.get('uid'),
                'source_ip': flow.get('id.orig_h'),
                'destination_ip': flow.get('id.resp_h'),
                'source_port': flow.get('id.orig_p'),
                'destination_port': flow.get('id.resp_p'),
                'protocol': flow.get('proto'),
                'service': flow.get('service'),
                'duration': flow.get('duration'),
                'orig_bytes': flow.get('orig_bytes'),
                'resp_bytes': flow.get('resp_bytes'),
                'conn_state': flow.get('conn_state')
            })
        return processed_flows
