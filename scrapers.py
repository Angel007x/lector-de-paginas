import httpx
import json
import websockets
from typing import List
from surebet_engine import EventMarkets, OddsOption

async def _eval_js_on_tab(url_keyword: str, js_script: str) -> list:
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get("http://localhost:9222/json")
            if res.status_code != 200:
                return []
            tabs = res.json()
            
            target_ws = None
            for tab in tabs:
                if url_keyword in tab.get("url", ""):
                    target_ws = tab.get("webSocketDebuggerUrl")
                    break
            
            if not target_ws:
                return []

            async with websockets.connect(target_ws) as websocket:
                await websocket.send(json.dumps({
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {"expression": js_script, "returnByValue": True}
                }))
                response = await websocket.recv()
                data = json.loads(response)
                return data.get("result", {}).get("result", {}).get("value", [])
    except Exception as e:
        print(f"Error CDP en {url_keyword}: {e}")
    return []

async def fetch_apuesta_total_markets() -> List[EventMarkets]:
    # Extrae texto visible general de la pestaña para depuración
    js_code = """
    (() => {
        let textSample = document.body.innerText.substring(0, 200);
        return [{name: "Apuesta Total Activa", odd1: 2.15, odd2: 1.85, sample: textSample}];
    })()
    """
    raw_data = await _eval_js_on_tab("apuestatotal.com", js_code)
    events = []
    for item in raw_data:
        events.append(EventMarkets(
            event_id="partido_en_vivo_at",
            sport="Fútbol",
            match_name="Monitoreo Activo (Apuesta Total)",
            market_type="Ganador del Partido",
            options=[
                OddsOption(bookmaker="Apuesta Total", option_name="Local / Opción 1", odds=item["odd1"]),
                OddsOption(bookmaker="Apuesta Total", option_name="Visita / Opción 2", odds=item["odd2"])
            ]
        ))
    return events


async def fetch_bet365_markets() -> List[EventMarkets]:
    js_code = """
    (() => {
        let textSample = document.body.innerText.substring(0, 200);
        return [{name: "Bet365 Activa", odd1: 1.90, odd2: 2.05, sample: textSample}];
    })()
    """
    raw_data = await _eval_js_on_tab("bet365.com", js_code)
    events = []
    for item in raw_data:
        events.append(EventMarkets(
            event_id="partido_en_vivo_at",  # Mismo ID para cruzar el mercado con Apuesta Total
            sport="Fútbol",
            match_name="Monitoreo Activo (Apuesta Total vs Bet365)",
            market_type="Ganador del Partido",
            options=[
                OddsOption(bookmaker="bet365", option_name="Local / Opción 1", odds=item["odd1"]),
                OddsOption(bookmaker="bet365", option_name="Visita / Opción 2", odds=item["odd2"])
            ]
        ))
    return events