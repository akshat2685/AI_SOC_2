import os
import datetime
import requests
import psycopg2

class SOARAutomationEngine:
    def __init__(self, db_url=None, api_key=None, endpoint=None):
        self.db_url = db_url or os.environ.get("DATABASE_URL", "postgresql://user:password@localhost:5432/ai_soc")
        self.api_key = api_key or os.environ.get("SOAR_API_KEY", "dummy_key")
        self.endpoint = endpoint or os.environ.get("SOAR_API_ENDPOINT", "https://api.example.com/v1/containment")

    def _log_to_db(self, risk_score: int, action: str, status: str, response: dict = None):
        try:
            conn = psycopg2.connect(self.db_url)
            cursor = conn.cursor()
            query = """
            INSERT INTO response_actions (timestamp, risk_score, action, status, api_response)
            VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(query, (
                datetime.datetime.now(),
                risk_score,
                action,
                status,
                str(response) if response else None
            ))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"[SOAR] DB Logging failed: {e}")

    def evaluate_risk_policy(self, risk_score: int, action: str, payload: dict = None):
        """
        Risk-Based Autonomous Response
        0-30: Automatic execution (Low Risk)
        31-70: Approval required (Medium Risk)
        71-100: Human escalation (High Risk)
        """
        if risk_score <= 30:
            return self._execute_automatic(risk_score, action, payload)
        elif risk_score <= 70:
            return self._request_approval(risk_score, action)
        else:
            return self._escalate_to_human(risk_score, action)

    def _execute_automatic(self, risk_score: int, action: str, payload: dict):
        print(f"[SOAR] Auto-executing low risk action: {action}")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        api_response = None
        status = "executed"
        
        try:
            # Staged API request for containment
            response = requests.post(
                f"{self.endpoint}/{action}", 
                headers=headers, 
                json=payload or {"reason": "auto-containment"},
                timeout=10
            )
            response.raise_for_status()
            api_response = response.json()
        except Exception as e:
            status = "failed"
            api_response = {"error": str(e)}
            print(f"[SOAR] API execution failed: {e}")

        self._log_to_db(risk_score, action, status, api_response)
        return {"status": status, "action": action, "response": api_response}

    def _request_approval(self, risk_score: int, action: str):
        print(f"[SOAR] Requesting approval for medium risk action: {action}")
        status = "pending_approval"
        self._log_to_db(risk_score, action, status)
        return {"status": status, "action": action}

    def _escalate_to_human(self, risk_score: int, action: str):
        print(f"[SOAR] ESCALATION REQUIRED for high risk action: {action}")
        status = "escalated"
        self._log_to_db(risk_score, action, status)
        return {"status": status, "action": action}
