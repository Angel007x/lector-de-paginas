import asyncio
import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from time import perf_counter
from urllib.parse import urlsplit
from browser_manager import BrowserManager


URL = (
    "https://www.apuestatotal.com/"
    "apuestas-deportivas/?fpath=/es-pe/spbkv3/sports/1/"
)

FRAME_DOMAIN = "prod20392.kmianko.com"

# Zona horaria de Perú
TIMEZONE = ZoneInfo("America/Lima")

# Máximo de horas hacia adelante
MAX_HOURS = 6

SELECTORS = {
    "participants": "[class*='Participant_participantName']",

    "event_card": "[data-component='event-card']",

    "event_date": "[data-part='start-date']",

    "event_status": "[data-component='event-card']",

    "event_participants": "[data-part='participant-name']",

    "market": '[data-component="market"]',

    "market_name": (
        ".eventpage_fe_Markets_marketNameText"
    ),

    "team_name": (
        ".eventpage_fe_MoneyLineSelection_meaning"
    ),

    "team_odds": (
        ".eventpage_fe_MoneyLineSelection_odds"
    ),

    "double_name": (
        ".eventpage_fe_OtherSelection_name"
    ),

    "double_odds": (
        ".eventpage_fe_OtherSelection_odds"
    ),
}


def clean_text(value):
    return " ".join(value.split()).strip()


def parse_odds(value):

    value = clean_text(value)

    match = re.search(r"\d+(?:[.,]\d+)?", value)

    if not match:
        return None

    return float(match.group().replace(",", "."))


async def inspect_json_response(response, counter):

    if counter[0] >= 30:
        return

    try:

        content_type = response.headers.get(
            "content-type", ""
        ).lower()

        if "json" not in content_type:
            return

        counter[0] += 1

        data = await response.json()

        parsed_url = urlsplit(response.url)

        # Solo mostrar nombres de campos, nunca valores sensibles
        if isinstance(data, dict):

            keys = list(data.keys())[:25]

        elif isinstance(data, list) and data:

            keys = (
                list(data[0].keys())[:25]
                if isinstance(data[0], dict)
                else ["Respuesta tipo lista"]
            )

        else:

            keys = ["Respuesta JSON sin estructura conocida"]

        print("\n" + "-" * 55)
        print("RESPUESTA JSON DETECTADA")
        print("-" * 55)

        print("URL:", parsed_url.netloc + parsed_url.path)
        print("Estado HTTP:", response.status)
        print("Campos:", keys)

    except Exception:
        pass


async def find_sports_frame(page):

    for frame in page.frames:

        if FRAME_DOMAIN in frame.url:
            return frame

    return None


def parse_event_datetime(date_text, now):

    """
    Convierte fechas como:
    10/11 • 18:30

    Utiliza el año actual y la zona horaria de Perú.
    """

    match = re.search(
        r"(\d{1,2})/(\d{1,2})\s*[•·]\s*(\d{1,2}):(\d{2})",
        date_text
    )

    if not match:
        return None

    day = int(match.group(1))
    month = int(match.group(2))
    hour = int(match.group(3))
    minute = int(match.group(4))

    try:

        return datetime(
            year=now.year,
            month=month,
            day=day,
            hour=hour,
            minute=minute,
            tzinfo=TIMEZONE
        )

    except ValueError:

        return None




async def get_filtered_events(frame):

    now = datetime.now(TIMEZONE)
    today = now.date()

    events = frame.locator(SELECTORS["event_card"])
    total = await events.count()

    selected_events = []
    processed = set()

    stats = {
        "total": total,
        "prematch": 0,
        "live": 0,
        "other": 0,
        "invalid": 0,
        "wrong_date": 0,
        "duplicates": 0,
        "selected": 0
    }

    print("\n" + "=" * 50)
    print("FILTRO DE PARTIDOS")
    print("=" * 50)

    print(f"Fecha actual: {now.strftime('%d/%m/%Y')}")
    print(f"Hora actual: {now.strftime('%H:%M')}")
    print(f"Tarjetas encontradas: {total}")

    for i in range(total):

        event = events.nth(i)

        try:

            # 1. Estado del partido
            status = await event.get_attribute("data-state")

            if status == "live":
                stats["live"] += 1
                continue

            if status != "prematch":
                stats["other"] += 1
                continue

            stats["prematch"] += 1

            # 2. Obtener participantes en una sola consulta
            participants = event.locator(
                SELECTORS["event_participants"]
            )

            names = await participants.all_inner_texts()

            teams = []

            for name in names:

                name = clean_text(name)

                if name and name not in teams:
                    teams.append(name)

                if len(teams) == 2:
                    break

            if len(teams) < 2:
                stats["invalid"] += 1
                continue

            team_a = teams[0]
            team_b = teams[1]

            # 3. Obtener fecha
            date_locator = event.locator(
                SELECTORS["event_date"]
            )

            date_text = clean_text(
                await date_locator.first.inner_text()
            ) if await date_locator.count() else ""

            if not date_text:
                stats["invalid"] += 1
                continue

            event_datetime = parse_event_datetime(
                date_text,
                now
            )

            if event_datetime is None:
                stats["invalid"] += 1
                continue

            # 4. Solo partidos de hoy
            if event_datetime.date() != today:
                stats["wrong_date"] += 1
                continue

            # 5. Evitar partidos cuya hora ya pasó
            if event_datetime < now:
                stats["wrong_date"] += 1
                continue

            # 6. Evitar duplicados
            event_key = (
                event_datetime.date().isoformat(),
                team_a.casefold(),
                team_b.casefold()
            )

            if event_key in processed:
                stats["duplicates"] += 1
                continue

            processed.add(event_key)

            # 7. Guardar partido y referencia a su tarjeta
            selected_events.append({

                "equipo_a": team_a,
                "equipo_b": team_b,
                "fecha_inicio": event_datetime.isoformat(),
                "fecha_texto": date_text,
                "locator": event

            })

            stats["selected"] += 1

        except Exception as error:

            stats["invalid"] += 1

            print(
                f"Error leyendo partido {i + 1}: {error}"
            )

    # Resumen
    print("\n" + "=" * 50)
    print("RESUMEN")
    print("=" * 50)

    print(f"Tarjetas totales: {stats['total']}")
    print(f"Prematch: {stats['prematch']}")
    print(f"En vivo excluidos: {stats['live']}")
    print(f"Otros estados excluidos: {stats['other']}")
    print(f"Fechas excluidas: {stats['wrong_date']}")
    print(f"Datos inválidos: {stats['invalid']}")
    print(f"Duplicados: {stats['duplicates']}")

    print(f"\nPARTIDOS SELECCIONADOS: {stats['selected']}")

    print("=" * 50)

    return selected_events




async def extract_markets(frame):

    result = {
        "resultado_partido_supercuota": [],
        "resultado_partido_normal": [],
        "doble_oportunidad": []
    }

    markets = frame.locator(SELECTORS["market"])

    # Obtener todos los nombres de mercados en una consulta
    market_names = await markets.locator(
        SELECTORS["market_name"]
    ).all_inner_texts()

    for i, name in enumerate(market_names):

        market_name = clean_text(name).casefold()

        # --------------------------------
        # IDENTIFICAR MERCADOS NECESARIOS
        # --------------------------------

        if (
            "resultado del partido" in market_name
            and "1x2" in market_name
        ):

            if "supercuota" in market_name:
                target_market = "resultado_partido_supercuota"
                button_selector = (
                    ".eventpage_fe_MoneyLineSelection_line"
                )
                name_selector = SELECTORS["team_name"]
                odds_selector = SELECTORS["team_odds"]

            else:
                target_market = "resultado_partido_normal"
                button_selector = (
                    ".eventpage_fe_MoneyLineSelection_line"
                )
                name_selector = SELECTORS["team_name"]
                odds_selector = SELECTORS["team_odds"]

        elif "doble oportunidad" in market_name:

            target_market = "doble_oportunidad"
            button_selector = (
                ".eventpage_fe_OtherSelection_line"
            )
            name_selector = SELECTORS["double_name"]
            odds_selector = SELECTORS["double_odds"]

        else:
            # Ignorar mercados que no necesitamos
            continue

        # --------------------------------
        # EXTRAER SELECCIONES Y CUOTAS
        # --------------------------------

        market = markets.nth(i)

        buttons = market.locator(button_selector)

        selections = await buttons.locator(
            name_selector
        ).all_inner_texts()

        odds_values = await buttons.locator(
            odds_selector
        ).all_inner_texts()

        # Asociar selecciones con sus cuotas
        for selection, odds_text in zip(selections, odds_values):

            selection = clean_text(selection)
            odds = parse_odds(odds_text)

            if selection and odds is not None:

                result[target_market].append({

                    "seleccion": selection,
                    "cuota": odds

                })

    return result




async def inspect_all_event_cards(frame):

    selectors = [
        "li.master_fe_Carousel_listItem",
        "[data-component='event-card']"
    ]

    inspected = []
    seen = set()

    for selector in selectors:

        events = frame.locator(selector)
        total = await events.count()

        print(f"\nSELECTOR: {selector}")
        print(f"Elementos encontrados: {total}")

        for i in range(total):

            event = events.nth(i)

            try:

                html = await event.inner_html()
                card_text = clean_text(await event.inner_text())

                # Evitar guardar dos veces la misma tarjeta
                if html in seen:
                    continue

                seen.add(html)

                # Estado: buscar primero en el contenedor
                status = await event.get_attribute("data-state")

                if not status:
                    info = event.locator(
                        "[data-component='featured-event-info']"
                    )

                    if await info.count():
                        status = await info.first.get_attribute(
                            "data-state"
                        )

                # Buscar participantes en todas las estructuras conocidas
                participants = event.locator(
                    "[data-part='participant-name'], "
                    "[data-component='featured-participant'], "
                    "[class*='Participant_participantName']"
                )

                names = []

                for j in range(await participants.count()):

                    name = clean_text(
                        await participants.nth(j).inner_text()
                    )

                    if name and name not in names:
                        names.append(name)

                    if len(names) >= 2:
                        break

                # Nombres alternativos
                alternative_teams = []

                alternative_selectors = [
                    "h3",
                    "[data-part='name']",
                    "[data-part='title']",
                    "[class*='Participant_participant']"
                ]

                for alt_selector in alternative_selectors:

                    loc = event.locator(alt_selector)

                    for j in range(await loc.count()):

                        name = clean_text(
                            await loc.nth(j).inner_text()
                        )

                        if (
                            name
                            and name.casefold() != "vs"
                            and name not in alternative_teams
                        ):
                            alternative_teams.append(name)

                # Fecha y hora
                date_selectors = [
                    "[data-part='date']",
                    "[data-part='time']",
                    "[data-component='event-time']"
                ]

                date_text = None

                for date_selector in date_selectors:

                    loc = event.locator(date_selector)

                    if await loc.count():

                        date_text = clean_text(
                            await loc.first.inner_text()
                        )

                        if date_text:
                            break
                        status_locator = event.locator(
                SELECTORS["event_status"]
                )

                date_locator = event.locator(
                SELECTORS["event_date"]
                )

                participants = event.locator(
                SELECTORS["event_participants"]
                )



                # Competición
                league_selectors = [
                    "[data-part='league-name']",
                    "[data-component='featured-event-name']"
                ]

                league = None

                for league_selector in league_selectors:

                    loc = event.locator(league_selector)

                    if await loc.count():

                        league = clean_text(
                            await loc.first.inner_text()
                        )

                        if league:
                            break

                unavailable_message = (
                    "no disponible" in card_text.casefold()
                    or "not available" in card_text.casefold()
                )

                inspected.append({

                    "indice": i,
                    "selector_origen": selector,
                    "estado": status,
                    "fecha": date_text,
                    "competicion": league,
                    "participantes": names,
                    "nombres_alternativos": alternative_teams,
                    "clase": await event.get_attribute("class"),
                    "mensaje_sin_mercado": unavailable_message,
                    "texto_tarjeta": card_text,
                    "html": html

                })

            except Exception as error:

                inspected.append({
                    "indice": i,
                    "selector_origen": selector,
                    "error": str(error)
                })

    with open(
        "diagnostico_eventos.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            inspected,
            file,
            ensure_ascii=False,
            indent=2
        )

    print(
        f"\nDiagnóstico guardado: {len(inspected)} eventos"
    )



async def inspect_all_sports_events(frame):

    print("\n" + "=" * 60)
    print("DIAGNÓSTICO GENERAL DEL FRAME")
    print("=" * 60)

    selectors = [
        "li.master_fe_Carousel_listItem",
        "[data-component='event-card']",
        "[data-component='featured-event-name']",
        "[data-component='featured-participant']",
        "[class*='EventName_eventName']",
        "[class*='eventlist']",
        "[class*='Carousel']",
    ]

    for selector in selectors:

        locator = frame.locator(selector)

        try:
            count = await locator.count()

            print(f"\nSELECTOR: {selector}")
            print(f"Elementos encontrados: {count}")

        except Exception as error:

            print(f"Error: {error}")

    # Buscar directamente los textos de los partidos
    body_text = await frame.locator("body").inner_text()

    keywords = [
        "E-Soccer",
        "Trindade",
        "Guarani Juazeiro",
        "Liverpool Montevideo",
        "Este mercado no está disponible",
    ]

    print("\n" + "=" * 60)
    print("BÚSQUEDA DE PARTIDOS EN EL FRAME")
    print("=" * 60)

    for keyword in keywords:

        found = keyword.casefold() in body_text.casefold()

        print(f"{keyword}: {'ENCONTRADO' if found else 'NO ENCONTRADO'}")

    with open(
        "diagnostico_frame_completo.txt",
        "w",
        encoding="utf-8"
    ) as file:

        file.write(body_text)

    print("\nTexto completo guardado en diagnostico_frame_completo.txt")




async def main():

    browser = BrowserManager()

    all_events = []
    saved_events = set()

    start_total = perf_counter()

    processed_count = 0
    total_processing_time = 0

    try:

        await browser.start()

        page = await browser.open_page(
            "apuesta_total",
            URL
        )




        # --------------------------------
        # CAPTURA DE LAS API
        # --------------------------------

        async def monitor_respuestas(response):

            url = response.url

            if "api/eventlist/eu/markets/all" in url:
                tipo = "markets"

            elif "api/pulse/snapshot/events" in url:
                tipo = "events"

            elif "api/sportscenter/carousels/events-with-items" in url:
                tipo = "events_with_items"

            else:
                return

            try:

                if response.status != 200:
                    return

                data = await response.json()

                archivos = {
                    "markets": "captura_markets.jsonl",
                    "events": "captura_events.jsonl",
                    "events_with_items": "captura_events_with_items.jsonl"
                }

                registro = {
                    "tipo": tipo,
                    "url": url,
                    "status": response.status,
                    "fecha_captura": datetime.now(
                        TIMEZONE
                    ).isoformat(),
                    "data": data
                }

                with open(
                    archivos[tipo],
                    "a",
                    encoding="utf-8"
                ) as file:

                    file.write(
                        json.dumps(
                            registro,
                            ensure_ascii=False
                        ) + "\n"
                    )

                cantidad = (
                    len(data)
                    if isinstance(data, list)
                    else len(data.get("data", {}))
                    if isinstance(data, dict)
                    and isinstance(data.get("data"), (list, dict))
                    else "Objeto"
                )

                print(
                    f"\nAPI CAPTURADA: {tipo} | "
                    f"Registros: {cantidad} | "
                    f"HTTP: {response.status}"
                )

            except Exception as error:

                print(
                    f"Error capturando API {tipo}: {error}"
                )

        page.on(
            "response",
            lambda response: asyncio.create_task(
                monitor_respuestas(response)
            )
        )

        print("Monitor de tres API activado.")



        print("\nEsperando carga de eventos...")

        # --------------------------------
        # ESPERAR FRAME DEPORTIVO
        # --------------------------------

        frame = None
        deadline = perf_counter() + 30

        while perf_counter() < deadline:

            frame = await find_sports_frame(page)

            if frame:
                break

            await asyncio.sleep(0.25)

        if not frame:
            print("No se encontró el frame deportivo.")
            return

        try:

            await frame.locator(
                SELECTORS["event_card"]
            ).first.wait_for(
                state="visible",
                timeout=15000
            )

        except Exception:

            print("No aparecieron las tarjetas.")
            return

        print("\nFrame deportivo encontrado.")

        # --------------------------------
        # FILTRAR PARTIDOS
        # --------------------------------

        event_names = await get_filtered_events(frame)

        if not event_names:

            print("\nNo hay partidos que cumplan los filtros.")
            return

        total_events = len(event_names)

        print(
            f"\nPartidos que se procesarán: {total_events}"
        )

        # --------------------------------
        # PROCESAR PARTIDOS
        # --------------------------------

        for index, event_info in enumerate(event_names):

            event_start = perf_counter()

            equipo_a = event_info["equipo_a"]
            equipo_b = event_info["equipo_b"]

            event_key = (
                event_info["fecha_inicio"],
                equipo_a.casefold(),
                equipo_b.casefold()
            )

            if event_key in saved_events:
                continue

            print("\n" + "=" * 50)

            print(
                f"[{index + 1}/{total_events}] "
                f"{equipo_a} vs {equipo_b}"
            )

            print("=" * 50)

            opened_event = False

            try:

                # --------------------------------
                # RECUPERAR FRAME ACTUAL
                # --------------------------------

                frame = await find_sports_frame(page)

                if not frame:

                    print("No se encontró el frame.")
                    break

                # Esperar tarjetas disponibles
                await frame.locator(
                    SELECTORS["event_card"]
                ).first.wait_for(
                    state="visible",
                    timeout=10000
                )

                # --------------------------------
                # BUSCAR PARTIDO ACTUAL
                # --------------------------------

                current_events = frame.locator(
                    SELECTORS["event_card"]
                )

                event_count = await current_events.count()

                found_event = None

                for i in range(event_count):

                    event = current_events.nth(i)

                    participants = event.locator(
                        SELECTORS["event_participants"]
                    )

                    names = await participants.all_inner_texts()

                    teams = [
                        clean_text(name)
                        for name in names
                        if clean_text(name)
                    ]

                    if len(teams) < 2:
                        continue

                    if (
                        teams[0].casefold() == equipo_a.casefold()
                        and teams[1].casefold() == equipo_b.casefold()
                    ):

                        found_event = event
                        break

                if found_event is None:

                    print("No se encontró la tarjeta actual.")
                    continue

                # --------------------------------
                # ABRIR PARTIDO
                # --------------------------------

                event_link = found_event.locator(
                    "button[data-part='event-name']"
                )

                if await event_link.count() == 0:

                    print("No se encontró el enlace.")
                    continue

                open_start = perf_counter()

                await event_link.first.click()
                print("\nURL DETALLE:", page.url)
                await asyncio.sleep(1)

                print("URL:", page.url)

                print(
                    "Tarjetas visibles:",
                    await frame.locator(
                        SELECTORS["event_card"]
                    ).count()
                )
                print("FRAME:", frame.url)
                print(
                    "Mercados visibles:",
                    await frame.locator(
                        SELECTORS["market"]
                    ).count()
                )
                                
                

                opened_event = True

                try:

                    await frame.locator(
                        SELECTORS["market"]
                    ).first.wait_for(
                        state="visible",
                        timeout=10000
                    )

                except Exception:
                    pass

                open_time = perf_counter() - open_start

                # Recuperar frame de detalle
                frame = await find_sports_frame(page)

                if not frame:

                    print("No se encontró el frame del partido.")
                    break

                # --------------------------------
                # EXTRAER MERCADOS
                # --------------------------------

                extraction_start = perf_counter()

                markets = await extract_markets(frame)

                extraction_time = (
                    perf_counter() - extraction_start
                )

                # --------------------------------
                # VALIDAR RESULTADO 1X2
                # --------------------------------

                if not (
                    markets["resultado_partido_supercuota"]
                    or markets["resultado_partido_normal"]
                ):

                    print("PARTIDO OMITIDO: No hay cuotas 1X2.")

                else:

                    # --------------------------------
                    # GUARDAR RESULTADOS
                    # --------------------------------

                    event_data = {

                        "partido": f"{equipo_a} vs {equipo_b}",

                        "equipo_a": equipo_a,
                        "equipo_b": equipo_b,

                        "fecha_inicio": event_info["fecha_inicio"],

                        "resultado_partido_supercuota":
                            markets["resultado_partido_supercuota"],

                        "resultado_partido_normal":
                            markets["resultado_partido_normal"],

                        "doble_oportunidad":
                            markets["doble_oportunidad"],

                        "fecha_extraccion":
                            datetime.now(TIMEZONE).isoformat()

                    }

                    all_events.append(event_data)
                    saved_events.add(event_key)

                    processed_count += 1

                    # --------------------------------
                    # INFORMACIÓN RESUMIDA
                    # --------------------------------

                    resultado = (
                        markets["resultado_partido_supercuota"]
                        or markets["resultado_partido_normal"]
                    )

                    print(
                        f"Resultado partido: {len(resultado)} cuotas"
                    )

                    print(
                        "Supercuota: "
                        + (
                            "DISPONIBLE"
                            if markets["resultado_partido_supercuota"]
                            else "NO DISPONIBLE"
                        )
                    )

                    print(
                        "Doble oportunidad: "
                        + (
                            "DISPONIBLE"
                            if markets["doble_oportunidad"]
                            else "NO DISPONIBLE"
                        )
                    )

                    # --------------------------------
                    # GUARDADO PROGRESIVO
                    # --------------------------------

                    with open(
                        "cuotas_apuesta_total.json",
                        "w",
                        encoding="utf-8"
                    ) as file:

                        json.dump(
                            all_events,
                            file,
                            ensure_ascii=False,
                            indent=2
                        )

                # --------------------------------
                # REGRESAR A LA LISTA
                # --------------------------------

                return_start = perf_counter()

                await page.go_back()
                
                opened_event = False

                frame = None
                deadline = perf_counter() + 15

                while perf_counter() < deadline:

                    frame = await find_sports_frame(page)

                    if frame:
                        break

                    await asyncio.sleep(0.25)

                if not frame:

                    print("No se pudo recuperar la lista.")
                    break

                await frame.locator(
                    SELECTORS["event_card"]
                ).first.wait_for(
                    state="visible",
                    timeout=10000
                )

                return_time = perf_counter() - return_start

                # --------------------------------
                # MEDICIÓN
                # --------------------------------

                event_time = perf_counter() - event_start

                total_processing_time += event_time

                print(f"\nTiempo apertura: {open_time:.2f}s")
                print(f"Tiempo extracción: {extraction_time:.2f}s")
                print(f"Tiempo regreso: {return_time:.2f}s")
                print(f"Tiempo total partido: {event_time:.2f}s")

            except Exception as error:

                print(
                    f"Error procesando {equipo_a} vs {equipo_b}: "
                    f"{error}"
                )

                # Recuperar lista si ocurrió un error
                # mientras estábamos dentro del partido
                if opened_event:

                    try:

                        await page.go_back()

                        opened_event = False

                        frame = None
                        deadline = perf_counter() + 15

                        while perf_counter() < deadline:

                            frame = await find_sports_frame(page)

                            if frame:
                                break

                            await asyncio.sleep(0.25)

                        if frame:

                            await frame.locator(
                                SELECTORS["event_card"]
                            ).first.wait_for(
                                state="visible",
                                timeout=10000
                            )

                        else:

                            print("No se pudo recuperar la lista.")
                            break

                    except Exception as recovery_error:

                        print(
                            f"Error recuperando la lista: "
                            f"{recovery_error}"
                        )

                        break

                continue

        # --------------------------------
        # RESUMEN FINAL
        # --------------------------------

        total_time = perf_counter() - start_total

        print("\n" + "=" * 50)
        print("EXTRACCIÓN FINALIZADA")
        print("=" * 50)

        print(f"Partidos seleccionados: {total_events}")
        print(f"Partidos guardados: {len(all_events)}")

        print(
            f"Tiempo total: {total_time:.2f} segundos"
        )

        print(
            f"Tiempo total: {total_time / 60:.2f} minutos"
        )

        print(
            f"Tiempo procesando partidos: "
            f"{total_processing_time:.2f} segundos"
        )

        if processed_count:

            print(
                f"Promedio por partido guardado: "
                f"{total_processing_time / processed_count:.2f} segundos"
            )

        print("Archivo: cuotas_apuesta_total.json")

        print("=" * 50)

        await asyncio.sleep(5)

    finally:

        await browser.close()


if __name__ == "__main__":

    asyncio.run(main())

