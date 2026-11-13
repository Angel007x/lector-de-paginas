
import asyncio
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from time import perf_counter
from urllib.parse import urlsplit

from browser_manager import BrowserManager


# ==========================================
# CONFIGURACION
# ==========================================

URL = (
    "https://www.apuestatotal.com/"
    "apuestas-deportivas/?fpath=/es-pe/spbkv3/sports/1/"
)

TIMEZONE = ZoneInfo("America/Lima")

OUTPUT_FILE = "cuotas_api_rapida.json"

EVENTS_ENDPOINT = "api/pulse/snapshot/events"

DETAIL_ENDPOINT = "api/eventpage/events/"

DETAIL_PARAMS = "?hideX25X75Selections=false"

MAX_CONCURRENT_REQUESTS = 8

captured_events = None
API_BASE = None


# ==========================================
# CAPTURAR EVENTOS
# ==========================================

async def monitor_response(response):

    global captured_events, API_BASE

    if EVENTS_ENDPOINT not in response.url:
        return

    if response.status != 200:
        print(f"Error snapshot: HTTP {response.status}")
        return

    try:
        captured_events = await response.json()

        parsed = urlsplit(response.url)

        API_BASE = f"{parsed.scheme}://{parsed.netloc}"

    except Exception as error:
        print(f"Error leyendo snapshot: {error}")


# ==========================================
# OBTENER LISTA DE EVENTOS
# ==========================================

def find_event_list(data):

    if isinstance(data, list):

        if data and isinstance(data[0], dict):

            if "_id" in data[0] and "StartEventDate" in data[0]:
                return data

        for item in data:

            result = find_event_list(item)

            if result is not None:
                return result

    elif isinstance(data, dict):

        for value in data.values():

            result = find_event_list(value)

            if result is not None:
                return result

    return None


# ==========================================
# CONVERTIR FECHAS
# ==========================================

def parse_event_date(value):

    if isinstance(value, (int, float)):

        return datetime.fromtimestamp(
            value / 1000,
            timezone.utc
        ).astimezone(TIMEZONE)

    if isinstance(value, str):

        try:

            parsed = datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )

            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)

            return parsed.astimezone(TIMEZONE)

        except ValueError:
            return None

    return None


# ==========================================
# FILTRAR EVENTOS
# ==========================================

def valid_event(event, now):

    if str(event.get("SportId")) != "1":
        return False

    if str(event.get("SportName", "")).casefold() not in (
        "fútbol",
        "futbol"
    ):
        return False

    if event.get("IsLive") is True:
        return False

    if event.get("IsSuspended") is True:
        return False

    event_date = parse_event_date(
        event.get("StartEventDate")
    )

    if event_date is None:
        return False

    if event_date.date() != now.date():
        return False

    if event_date <= now:
        return False

    return True


# ==========================================
# NORMALIZAR NOMBRES
# ==========================================

def localized_name(value):

    if isinstance(value, dict):

        return (
            value.get("ES-PE")
            or value.get("ES")
            or next(iter(value.values()), "")
        )

    return value or ""


# ==========================================
# EXTRAER SELECCIONES
# ==========================================

def extract_selections(selections):

    results = []

    if not isinstance(selections, list):
        return results

    for selection in selections:

        if not isinstance(selection, list):
            continue

        if len(selection) < 8:
            continue

        # Selección deshabilitada
        if selection[5] is True:
            continue

        # Selección eliminada
        if selection[7] is True:
            continue

        try:
            odds = float(selection[6])

        except (TypeError, ValueError):
            continue

        if odds <= 1:
            continue

        results.append({
            "selection_id": selection[0],
            "nombre": localized_name(selection[1]),
            "cuota": odds
        })

    return results


# ==========================================
# EXTRAER LOS TRES MERCADOS
# ==========================================

def extract_markets(detail, expected_event_id=None):

    output = {
        "resultado_partido": None,
        "resultado_partido_supercuota": None,
        "doble_oportunidad": None
    }

    data = detail.get("data", [])

    if not isinstance(data, list):
        return output

    event_row = None

    for row in data:

        if not isinstance(row, list):
            continue

        if len(row) <= 20:
            continue

        if expected_event_id is not None:

            if str(row[0]) != str(expected_event_id):
                continue

        event_row = row
        break

    if event_row is None:
        return output

    markets = event_row[20]

    if not isinstance(markets, list):
        return output

    for market in markets:

        if not isinstance(market, list):
            continue

        if len(market) <= 13:
            continue

        market_type = market[5]

        if not isinstance(market_type, list):
            continue

        if not market_type:
            continue

        market_code = market_type[0]

        # Solo procesamos los tres mercados necesarios
        if market_code not in ("ML0", "ML5000", "QA61"):
            continue

        # Comprobar suspensión o eliminación
        if market[14] is True or market[15] is True:
            continue

        selections = extract_selections(market[13])

        if not selections:
            continue

        market_data = {
            "market_id": market[0],
            "market_type_id": market_code,
            "nombre": localized_name(market[1]),
            "cuotas": selections
        }

        if market_code == "ML0":

            output["resultado_partido"] = market_data

        elif market_code == "ML5000":

            output["resultado_partido_supercuota"] = market_data

        elif market_code == "QA61":

            output["doble_oportunidad"] = market_data

    return output


# ==========================================
# CONSULTAR DETALLE DE PARTIDO
# ==========================================

async def get_event_detail(page, event, semaphore):

    event_id = str(event["_id"])

    endpoint = (
        f"{API_BASE}/{DETAIL_ENDPOINT}"
        f"{event_id}{DETAIL_PARAMS}"
    )

    async with semaphore:

        try:

            response = await page.request.get(
                endpoint,
                headers={
                    "Accept": "application/json",
                    "Referer": URL
                },
                timeout=30000
            )

            if response.status != 200:

                return {
                    "event_id": event_id,
                    "error": f"HTTP {response.status}",
                    "resultado_partido": None,
                    "resultado_partido_supercuota": None,
                    "doble_oportunidad": None
                }

            detail = await response.json()

            markets = extract_markets(
                detail,
                expected_event_id=event_id
            )

            participants = event.get("Participants", [])

            team_a = (
                participants[0].get("Name", "")
                if len(participants) > 0 else ""
            )

            team_b = (
                participants[1].get("Name", "")
                if len(participants) > 1 else ""
            )

            event_date = parse_event_date(
                event.get("StartEventDate")
            )

            return {

                "event_id": event_id,

                "partido": f"{team_a} vs {team_b}",

                "deporte": event.get("SportName"),

                "liga": event.get("LeagueName"),

                "fecha_inicio": (
                    event_date.isoformat()
                    if event_date else None
                ),

                "estado": "proximo",

                **markets

            }

        except Exception as error:

            return {
                "event_id": event_id,
                "error": str(error),
                "resultado_partido": None,
                "resultado_partido_supercuota": None,
                "doble_oportunidad": None
            }


# ==========================================
# PROCESAMIENTO PRINCIPAL
# ==========================================

async def process_events(page, events):

    now = datetime.now(TIMEZONE)

    selected = [
        event
        for event in events
        if valid_event(event, now)
    ]

    print("\n========== PROCESAMIENTO ==========")

    print("Eventos recibidos:", len(events))

    print("Partidos válidos de hoy:", len(selected))

    semaphore = asyncio.Semaphore(
        MAX_CONCURRENT_REQUESTS
    )

    start = perf_counter()

    tasks = [
        get_event_detail(
            page,
            event,
            semaphore
        )
        for event in selected
    ]

    results = await asyncio.gather(*tasks)

    elapsed = perf_counter() - start

    successful = sum(
        1 for result in results
        if "error" not in result
    )

    errors = len(results) - successful

    result_count = sum(
        1 for r in results
        if r.get("resultado_partido")
    )

    super_count = sum(
        1 for r in results
        if r.get("resultado_partido_supercuota")
    )

    double_count = sum(
        1 for r in results
        if r.get("doble_oportunidad")
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            results,
            file,
            ensure_ascii=False,
            indent=2
        )

    print("\n========== RESULTADOS ==========")

    print("Partidos consultados:", len(results))
    print("Detalles recibidos:", successful)
    print("Errores:", errors)

    print("Con Resultado partido:", result_count)
    print("Con Supercuota:", super_count)
    print("Con Doble oportunidad:", double_count)

    print("Tiempo de consultas:", round(elapsed, 2), "segundos")

    print("\nJSON generado:", OUTPUT_FILE)

    return results


# ==========================================
# MAIN
# ==========================================

async def main():

    global captured_events

    browser = BrowserManager()

    start = perf_counter()

    response_tasks = set()

    try:

        print("Iniciando navegador...")

        await browser.start()

        page = await browser.context.new_page()

        browser.pages["apuesta_total"] = page

        def schedule_response(response):

            task = asyncio.create_task(
                monitor_response(response)
            )

            response_tasks.add(task)

            task.add_done_callback(
                response_tasks.discard
            )

        # Registrar listener antes de navegar
        page.on("response", schedule_response)

        await page.goto(
            URL,
            wait_until="domcontentloaded"
        )

        print("Esperando snapshot de eventos...")

        deadline = perf_counter() + 30

        while (
            captured_events is None
            and perf_counter() < deadline
        ):

            await asyncio.sleep(0.25)

        if response_tasks:

            await asyncio.gather(
                *list(response_tasks),
                return_exceptions=True
            )

        if captured_events is None:

            print("ERROR: No se recibió snapshot.")

            return

        events = find_event_list(captured_events)

        if events is None:

            print("ERROR: No se encontró la lista de eventos.")

            return

        print("Snapshot recibido correctamente.")
        print("Eventos identificados:", len(events))

        await process_events(page, events)

        print(
            "\nTiempo total:",
            round(perf_counter() - start, 2),
            "segundos"
        )

    except Exception as error:

        print(f"ERROR GENERAL: {error}")

    finally:

        if response_tasks:

            await asyncio.gather(
                *list(response_tasks),
                return_exceptions=True
            )

        await browser.close()

        print("Navegador cerrado.")


if __name__ == "__main__":

    asyncio.run(main())
