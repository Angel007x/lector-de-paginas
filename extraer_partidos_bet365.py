
import re
import csv
from pathlib import Path

# ==========================================
# CONFIGURACIÓN
# ==========================================

ARCHIVO_ENTRADA = Path("respuesta_upcoming.txt")
ARCHIVO_SALIDA = Path("partidos_extraidos.csv")


def extraer_campos(bloque):
    """Extrae campos clave=valor de un registro."""

    campos = {}

    for coincidencia in re.finditer(
        r"(?:^|;)([A-Z0-9]+)=([^;|]*)",
        bloque
    ):
        clave = coincidencia.group(1)
        valor = coincidencia.group(2).strip()
        campos[clave] = valor

    return campos


def extraer_partidos(texto):

    partidos = {}

    # Separar registros mediante |
    bloques = texto.split("|")

    for bloque in bloques:

        bloque = bloque.strip()

        if not bloque:
            continue

        # Identificar registros PA o EV
        if not re.match(r"^(PA|EV);", bloque):
            continue

        datos = extraer_campos(bloque)

        fi = datos.get("FI", "").strip()

        # FI obligatorio y numérico
        if not fi.isdigit():
            continue

        nombre = (
            datos.get("FD")
            or datos.get("EX")
            or datos.get("NA")
            or "Sin nombre"
        )

        partidos[fi] = {
            "FI": fi,
            "Partido": nombre,
            "N2": datos.get("N2", ""),
            "N3": datos.get("N3", ""),
            "BC": datos.get("BC", "")
        }

    return list(partidos.values())


def main():

    print("=" * 60)
    print("EXTRACCIÓN DE PARTIDOS")
    print("=" * 60)

    if not ARCHIVO_ENTRADA.exists():
        print("[ERROR] No existe respuesta_upcoming.txt")
        return

    texto = ARCHIVO_ENTRADA.read_text(
        encoding="utf-8-sig"
    )

    print(f"\nTamaño del archivo: {len(texto):,} caracteres")

    partidos = extraer_partidos(texto)

    print(f"\nPartidos encontrados: {len(partidos)}")

    if not partidos:
        print("\nNo se encontraron eventos con FI.")
        return

    columnas = ["FI", "Partido", "N2", "N3", "BC"]

    with ARCHIVO_SALIDA.open(
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as archivo:

        escritor = csv.DictWriter(
            archivo,
            fieldnames=columnas
        )

        escritor.writeheader()
        escritor.writerows(partidos)

    print("\nPRIMEROS 20 PARTIDOS:")
    print("-" * 60)

    for i, partido in enumerate(partidos[:20], 1):

        print(
            f"{i:02d}. FI={partido['FI']} | "
            f"{partido['Partido']} | "
            f"BC={partido['BC']}"
        )

    print("\nArchivo generado:", ARCHIVO_SALIDA.resolve())


if __name__ == "__main__":
    main()
