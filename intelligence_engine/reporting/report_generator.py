import json

class ReportGenerator:
    """ Feature 8: Automated Security Report Generation """
    
    def generate_executive_report(self, incident_data: dict) -> str:
        """ Generates business impact and risk level report in Markdown """
        report = (
            f"# Executive Security Report\\n"
            f"**Risk Level:** {incident_data.get('risk_level', 'UNKNOWN')}\\n"
            f"**Business Impact:** {incident_data.get('impact', 'Evaluating...')}\\n"
            f"**Affected Assets:** {len(incident_data.get('assets', []))}\\n"
            f"**Recommendations:** {incident_data.get('recommendations', 'None')}"
        )
        return report
        
    def generate_technical_report(self, incident_data: dict) -> dict:
        """ Generates detailed technical JSON payload with IOCs and MITRE mappings """
        return {
            "timeline": incident_data.get("timeline", []),
            "iocs": incident_data.get("iocs", []),
            "mitre_mapping": incident_data.get("mitre_mapping", []),
            "evidence": incident_data.get("evidence", [])
        }
