
import json
from pathlib import Path
from collections import defaultdict

BASE = Path("diagnostico_api")

ARCHIVOS = {
    "markets": BASE / "api_markets.json",
    "events": BASE / "api_events.json",
    "events_with_items": BASE / "api_events_with_items.json",
}


def cargar(nombre, ruta):
    if not ruta.exists():
        print(f"\nNO ENCONTRADO: {ruta}")
        return []

    with open(ruta, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"\n{nombre}: {len(data)} capturas")
    return data


def mostrar_estructura(objeto, prefijo="", nivel=0):
    if nivel > 3:
        return

    if isinstance(objeto, dict):
        for key, value in objeto.items():
            ruta = f"{prefijo}.{key}" if prefijo else key

            if isinstance(value, dict):
                print("  " * nivel + ruta + " [OBJETO]")
                mostrar_estructura(value, ruta, nivel + 1)

            elif isinstance(value, list):
                print(
                    "  " * nivel
                    + f"{ruta} [LISTA: {len(value)}]"
                )

                if value and isinstance(value[0], (dict, list)):
                    mostrar_estructura(
                        value[0], ruta + "[0]", nivel + 1
                    )
            else:
                print(
                    "  " * nivel
                    + f"{ruta} [{type(value).__name__}]"
                )


def buscar_eventos(data):
    resultados = []

    def recorrer(obj):
        if isinstance(obj, dict):
            if "EventId" in obj:
                resultados.append(obj)

            for value in obj.values():
                if isinstance(value, (dict, list)):
                    recorrer(value)

        elif isinstance(obj, list):
            for item in obj:
                recorrer(item)

    recorrer(data)
    return resultados


def main():
    capturas = {}

    print("\n========== DIAGNOSTICO API ==========")

    for nombre, ruta in ARCHIVOS.items():
        capturas[nombre] = cargar(nombre, ruta)

    # ----------------------------------
    # INVESTIGAR ESTRUCTURA
    # ----------------------------------

    for nombre, registros in capturas.items():

        print("\n" + "=" * 60)
        print("ESTRUCTURA:", nombre.upper())
        print("=" * 60)

        if not registros:
            continue

        data = registros[0].get("data", [])

        if isinstance(data, dict):
            mostrar_estructura(data)

        elif isinstance(data, list) and data:
            mostrar_estructura(data[0])

    # ----------------------------------
    # AGRUPAR MERCADOS POR EVENT ID
    # ----------------------------------

    eventos = defaultdict(list)

    for captura in capturas["markets"]:
        for mercado in captura.get("data", []):
            event_id = mercado.get("EventId")

            if event_id:
                eventos[str(event_id)].append(mercado)

    print("\n" + "=" * 60)
    print("RESUMEN DE MERCADOS")
    print("=" * 60)

    print("Eventos encontrados:", len(eventos))

    # ----------------------------------
    # INVESTIGAR EVENTOS Y RELACIONES
    # ----------------------------------

    for nombre in ("events", "events_with_items"):

        print("\n" + "=" * 60)
        print("EVENTOS EN:", nombre.upper())
        print("=" * 60)

        encontrados = []

        for captura in capturas[nombre]:
            encontrados.extend(
                buscar_eventos(captura.get("data", []))
            )

        print("Objetos con EventId:", len(encontrados))

        for evento in encontrados[:3]:
            print("\nOBJETO DE EVENTO:")
            print(json.dumps(
                evento,
                ensure_ascii=False,
                indent=2
            )[:5000])

    # ----------------------------------
    # RESUMEN DE ESTADOS DE MERCADOS
    # ----------------------------------

    print("\n" + "=" * 60)
    print("ESTADOS DE MERCADOS")
    print("=" * 60)

    estados = defaultdict(int)

    for mercados in eventos.values():
        for mercado in mercados:
            estado = (
                mercado.get("IsLive"),
                mercado.get("IsSuspended"),
                mercado.get("IsRemoved")
            )
            estados[estado] += 1

    for estado, cantidad in estados.items():
        print(estado, ":", cantidad)

    print("\n========== FIN ==========")

    probar_union()



from datetime import datetime, timezone

def probar_union():

    markets_file = BASE / "api_markets.json"
    events_file = BASE / "api_events.json"

    with open(markets_file, encoding="utf-8") as f:
        market_captures = json.load(f)

    with open(events_file, encoding="utf-8") as f:
        event_captures = json.load(f)

    markets = defaultdict(list)

    for capture in market_captures:
        for market in capture.get("data", []):
            event_id = market.get("EventId")

            if event_id:
                markets[str(event_id)].append(market)

    events = {}

    for capture in event_captures:
        for event in capture.get("data", []):

            event_id = event.get("_id")

            if event_id:
                events[str(event_id)] = event

    print("\n========== PRUEBA DE UNION ==========")

    print("Eventos API:", len(events))
    print("Eventos con mercados:", len(markets))

    coincidencias = 0

    for event_id, event in events.items():

        event_markets = markets.get(event_id, [])

        if not event_markets:
            continue

        coincidencias += 1

        participants = event.get("Participants", [])

        equipos = [
            p.get("Name", "")
            for p in participants
        ]

        timestamp = event.get("StartEventDate")

        fecha = None

        if timestamp:
            fecha = datetime.fromtimestamp(
                timestamp / 1000,
                tz=timezone.utc
            ).isoformat()

        print("\n" + "=" * 50)
        print("EVENT ID:", event_id)
        print("PARTIDO:", " vs ".join(equipos))
        print("FECHA UTC:", fecha)
        print("DEPORTE:", event.get("SportName"))
        print("LIGA:", event.get("LeagueName"))
        print("EN VIVO:", event.get("IsLive"))
        print("SUSPENDIDO:", event.get("IsSuspended"))
        print("MERCADOS:", len(event_markets))

    print("\nCoincidencias:", coincidencias)
    print("====================================")


if __name__ == "__main__":
    main()
