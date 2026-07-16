import re

class IOCExtractor:
    def __init__(self, neo4j_session=None):
        self.neo4j_session = neo4j_session
        self.ip_pattern = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
        self.domain_pattern = re.compile(r'\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b')
        self.hash_pattern = re.compile(r'\b[A-Fa-f0-9]{32,64}\b')

    def extract(self, text):
        return {
            'ips': self.ip_pattern.findall(text),
            'domains': self.domain_pattern.findall(text),
            'hashes': self.hash_pattern.findall(text)
        }

    def save_to_neo4j(self, iocs):
        if not self.neo4j_session:
            print("No Neo4j session provided.")
            return

        for ip in iocs.get('ips', []):
            self.neo4j_session.run("MERGE (i:IP {value: $ip})", ip=ip)
        for domain in iocs.get('domains', []):
            self.neo4j_session.run("MERGE (d:Domain {value: $domain})", domain=domain)
        for h in iocs.get('hashes', []):
            self.neo4j_session.run("MERGE (h:Hash {value: $hash})", hash=h)
