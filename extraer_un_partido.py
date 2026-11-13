
import json
from collections import defaultdict

ARCHIVO = "mercados_un_partido_corregido.json"

with open(ARCHIVO, "r", encoding="utf-8") as f:
    datos = json.load(f)

partidos = defaultdict(lambda: defaultdict(list))

for item in datos:

    event_id = item.get("EventId")
    market_id = item.get("MarketId")

    if not event_id or not market_id:
        continue

    partidos[event_id][market_id].append(item)

print("\n========== MERCADOS ENCONTRADOS ==========\n")

for event_id, mercados in partidos.items():

    print("=" * 60)
    print("EVENT ID:", event_id)

    for market_id, selecciones in mercados.items():

        primero = selecciones[0]

        print("\nMARKET ID:", market_id)
        print("TYPE NAME:", primero.get("TypeName"))

        for s in selecciones:
            print(
                f"  {s.get('Name')} "
                f"| Cuota: {s.get('Decimal')} "
                f"| Deshabilitada: {s.get('IsDisabled')}"
            )

print("\nTOTAL PARTIDOS:", len(partidos))
