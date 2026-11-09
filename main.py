import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from scrapers import fetch_apuesta_total_markets, fetch_bet365_markets
from surebet_engine import calculate_surebet, EventMarkets

app = FastAPI()

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

manager = ConnectionManager()

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.websocket("/ws/surebets")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            at_events = await fetch_apuesta_total_markets()
            b365_events = await fetch_bet365_markets()
            
            market_map = {}
            for event in at_events + b365_events:
                if event.event_id not in market_map:
                    market_map[event.event_id] = EventMarkets(
                        event_id=event.event_id,
                        sport=event.sport,
                        match_name=event.match_name,
                        market_type=event.market_type,
                        options=[]
                    )
                market_map[event.event_id].options.extend(event.options)

            for event_id, unified_event in market_map.items():
                oportunidad = calculate_surebet(unified_event, total_stake=500.0)
                if oportunidad:
                    await websocket.send_json(oportunidad.model_dump())

            await asyncio.sleep(5)

    except WebSocketDisconnect:
        manager.disconnect(websocket)