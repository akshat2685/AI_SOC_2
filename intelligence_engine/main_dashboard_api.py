from fastapi import FastAPI, WebSocket, Query, WebSocketDisconnect
from typing import List
import asyncio
import random
from core.ws_manager import manager as ws_manager

app = FastAPI(title="AI SOC Dashboard API")

alerts = []

@app.get("/api/alerts")
def get_live_alerts():
    return {"alerts": alerts}

@app.post("/api/alerts")
def create_alert(alert: dict):
    alerts.append(alert)
    return {"status": "success"}

@app.get("/api/risk-heatmap")
def get_risk_heatmap():
    heatmap = [
        {"region": "US-East", "risk_score": random.randint(10, 100)},
        {"region": "EU-West", "risk_score": random.randint(10, 100)},
        {"region": "AP-South", "risk_score": random.randint(10, 100)},
    ]
    return {"heatmap": heatmap}

@app.get("/api/time-series")
def get_time_series():
    try:
        from core.clickhouse_writer import ClickHouseWriter
        import os
        # Use default config or env vars for ClickHouse
        host = os.getenv("CLICKHOUSE_HOST", "localhost")
        port = int(os.getenv("CLICKHOUSE_PORT", "8123"))
        writer = ClickHouseWriter(host=host, port=port)
        writer.connect()
        series = writer.get_time_series_analytics()
        return {"time_series": series}
    except Exception as e:
        return {"error": str(e), "time_series": []}

@app.websocket("/ws/alerts")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            if alerts:
                await websocket.send_json({"latest_alert": alerts[-1]})
            await asyncio.sleep(5)
    except Exception as e:
        print(f"WebSocket Error: {e}")

@app.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket, token: str = Query(...)):
    tenant_id = await ws_manager.connect(websocket, token)
    if tenant_id is None:
        return
    try:
        while True:
            data = await websocket.receive_text()
            # Not expecting client messages for now, just keep connection open
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, tenant_id)
    except Exception as e:
        print(f"WebSocket Notification Error: {e}")
        ws_manager.disconnect(websocket, tenant_id)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
