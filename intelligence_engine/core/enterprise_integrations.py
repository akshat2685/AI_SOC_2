import asyncio
import structlog
import json
import subprocess
import os
import time
import aiohttp
import urllib.parse
from typing import Dict, Any, Callable
from .event_bus import EventBus
from .secrets_provider import secrets_manager

logger = structlog.get_logger(__name__)

class CircuitBreakerOpenException(Exception):
    pass

class CircuitBreaker:
    def __init__(self, max_failures: int = 3, reset_timeout: int = 60):
        self.max_failures = max_failures
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.last_failure_time = 0
        self.state = "CLOSED" # CLOSED, OPEN, HALF_OPEN

    def _update_state(self):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.reset_timeout:
                self.state = "HALF_OPEN"

    def record_success(self):
        self.failures = 0
        self.state = "CLOSED"

    def record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.max_failures:
            self.state = "OPEN"

    async def call(self, func: Callable, *args, **kwargs):
        self._update_state()
        if self.state == "OPEN":
            raise CircuitBreakerOpenException("Circuit breaker is OPEN")

        # Exponential backoff parameters
        max_retries = 3
        base_delay = 1

        for attempt in range(max_retries):
            try:
                result = await func(*args, **kwargs)
                self.record_success()
                return result
            except aiohttp.ClientResponseError as e:
                if e.status == 429:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"429 Too Many Requests. Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    self.record_failure()
                    raise e
            except Exception as e:
                self.record_failure()
                raise e
        
        self.record_failure()
        raise Exception("Max retries exceeded")

class BaseIntegrationWorker:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.circuit_breaker = CircuitBreaker()

    async def start(self):
        pass

class ServiceNowWorker(BaseIntegrationWorker):
    async def start(self):
        await self.event_bus.subscribe("incident.create", self.handle_incident_create)
        await self.event_bus.subscribe("incident.update", self.handle_incident_update)
        await self.event_bus.subscribe("knowledge.search", self.handle_knowledge_search)
        logger.info("ServiceNowWorker started and subscribed to events.")

    def _get_connection_id(self):
        try:
            return secrets_manager.get_secret("servicenow", "connection_id")
        except Exception:
            conn_id = os.getenv("SERVICENOW_CONNECTION_ID")
            if not conn_id:
                raise ValueError("ServiceNow connection ID not configured")
            return conn_id

    async def _run_membrane_command(self, action: str, input_data: str):
        conn_id = self._get_connection_id()
        cmd = [
            "membrane", "action", "run", action,
            f"--connectionId={conn_id}",
            f"--input={input_data}"
        ]
        
        async def execute():
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                raise Exception(f"Membrane CLI failed: {stderr.decode()}")
            return stdout.decode()

        return await self.circuit_breaker.call(execute)

    async def handle_incident_create(self, event: dict):
        try:
            input_data = json.dumps({"title": event.get("title"), "description": event.get("description")})
            result = await self._run_membrane_command("create-incident", input_data)
            await self.event_bus.publish("incident.created.success", {"result": result})
        except Exception as e:
            logger.error(f"Failed to create ServiceNow incident: {e}")
            await self.event_bus.publish("incident.created.failure", {"error": str(e)})

    async def handle_incident_update(self, event: dict):
        pass

    async def handle_knowledge_search(self, event: dict):
        pass

class JiraWorker(BaseIntegrationWorker):
    async def start(self):
        await self.event_bus.subscribe("ticket.analyze", self.handle_ticket_analyze)
        await self.event_bus.subscribe("ticket.transition", self.handle_ticket_transition)
        await self.event_bus.subscribe("ticket.comment", self.handle_ticket_comment)
        logger.info("JiraWorker started and subscribed to events.")

    def _get_auth(self):
        def get_cred(env_key, secret_key):
            val = os.getenv(env_key)
            if not val:
                try:
                    val = secrets_manager.get_secret("jira", secret_key)
                except Exception:
                    pass
            return val
            
        jira_url = get_cred("JIRA_URL", "url")
        jira_email = get_cred("JIRA_EMAIL", "email")
        jira_api_token = get_cred("JIRA_API_TOKEN", "api_token")
        
        if not all([jira_url, jira_email, jira_api_token]):
            raise ValueError("Missing Jira credentials")
        return jira_url, jira_email, jira_api_token

    async def _make_api_call(self, method: str, endpoint: str, json_data: dict = None):
        jira_url, jira_email, jira_api_token = self._get_auth()
        auth_header = aiohttp.helpers.BasicAuth(jira_email, jira_api_token).encode()
        headers = {"Authorization": auth_header}
        
        async def execute():
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.request(method, f"{jira_url}{endpoint}", json=json_data) as response:
                    if response.status == 429:
                        response.raise_for_status() # Trigger circuit breaker 429 logic
                    if response.status >= 400:
                        raise Exception(f"Jira API error: {response.status} {await response.text()}")
                    return await response.json()
        
        return await self.circuit_breaker.call(execute)

    async def handle_ticket_analyze(self, event: dict):
        pass

    async def handle_ticket_transition(self, event: dict):
        ticket_id = str(event.get("ticket_id", ""))
        transition_id = event.get("transition_id")
        
        if not ticket_id or not transition_id:
            logger.error("Missing ticket_id or transition_id")
            return
            
        safe_ticket_id = urllib.parse.quote(ticket_id, safe='')
        try:
            await self._make_api_call("POST", f"/rest/api/3/issue/{safe_ticket_id}/transitions", {"transition": {"id": transition_id}})
            logger.info(f"Successfully transitioned ticket {ticket_id}")
        except Exception as e:
            logger.error(f"Failed to transition Jira ticket: {e}")

    async def handle_ticket_comment(self, event: dict):
        pass

class SlackWorker(BaseIntegrationWorker):
    async def start(self):
        await self.event_bus.subscribe("notification.alert", self.handle_alert)
        await self.event_bus.subscribe("notification.chatops", self.handle_chatops)
        logger.info("SlackWorker started and subscribed to events.")

    def _get_webhook_url(self):
        url = os.getenv("SLACK_WEBHOOK_URL")
        if not url:
            try:
                url = secrets_manager.get_secret("slack", "webhook_url")
            except Exception:
                pass
        if not url:
            raise ValueError("Slack webhook URL not configured")
        return url

    async def _send_message(self, blocks: list):
        webhook_url = self._get_webhook_url()
        
        async def execute():
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json={"blocks": blocks}) as response:
                    if response.status == 429:
                        response.raise_for_status()
                    if response.status >= 400:
                        raise Exception(f"Slack API error: {response.status} {await response.text()}")
                    return await response.text()
        
        return await self.circuit_breaker.call(execute)

    async def handle_alert(self, event: dict):
        alert_title = event.get("title", "Alert")
        alert_desc = event.get("description", "No description")
        severity = event.get("severity", "LOW")
        
        # Format using mrkdwn
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{severity} ALERT*: {alert_title}\n> {alert_desc}"
                }
            }
        ]
        try:
            await self._send_message(blocks)
            logger.info("Successfully sent Slack alert")
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")

    async def handle_chatops(self, event: dict):
        pass
