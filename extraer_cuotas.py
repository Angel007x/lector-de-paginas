
import asyncio
import json
from pathlib import Path

from browser_manager import BrowserManager


# ============================================================
# CONFIGURACION
# ============================================================

URL = (
    "https://www.apuestatotal.com/"
    "apuestas-deportivas/?fpath=/es-pe/spbkv3/sports/1/daily"
)

FRAME_DOMAIN = "prod20392.kmianko.com"

SELECTOR_PARTICIPANTES = (
    "[class*='Participant_participantName']"
)

MAX_PARTICIPANTES = 10
MAX_ANCESTROS = 8

ARCHIVO_DIAGNOSTICO = "diagnostico_dom.json"


# ============================================================
# FRAME
# ============================================================

def find_sports_frame(page):

    for frame in page.frames:

        if FRAME_DOMAIN in frame.url:
            return frame

    return None


# ============================================================
# DIAGNOSTICO DE ANCESTROS
# ============================================================

async def diagnosticar_participante(participante, indice):

    datos = await participante.evaluate(
        """
        (elemento) => {

            const limpiar = texto =>
                (texto || "").replace(/\\s+/g, " ").trim();

            const resultado = {
                indice: 0,
                participante: limpiar(elemento.innerText),
                ancestros: []
            };

            let actual = elemento;

            for (let nivel = 0;
                 actual && nivel < 8;
                 nivel++) {

                const participantes = Array.from(
                    actual.querySelectorAll(
                        "[class*='Participant_participantName']"
                    )
                ).map(x => limpiar(x.innerText));

                const fechas = Array.from(
                    actual.querySelectorAll(
                        '[data-component="event-time"], ' +
                        '[data-part="start-date"]'
                    )
                ).map(x => limpiar(x.innerText));

                const indicadoresLive = Array.from(
                    actual.querySelectorAll(
                        '[data-component="live-badge"]'
                    )
                ).map(x => limpiar(x.innerText));

                const ancestro = {

                    nivel: nivel,

                    etiqueta: actual.tagName,

                    clase: actual.className.toString(),

                    texto: limpiar(
                        actual.innerText
                    ).slice(0, 700),

                    participantes: participantes,

                    fechas: fechas,

                    indicadores_live: indicadoresLive,

                    html: actual.outerHTML.slice(0, 2500)

                };

                resultado.ancestros.push(ancestro);

                actual = actual.parentElement;
            }

            return resultado;
        }
        """
    )

    datos["indice"] = indice

    return datos


# ============================================================
# DIAGNOSTICO GENERAL
# ============================================================

async def diagnosticar_frame(frame):

    participantes = frame.locator(
        SELECTOR_PARTICIPANTES
    )

    total = await participantes.count()

    print("\n======================================")
    print("DIAGNOSTICO DEL FRAME DEPORTIVO")
    print("======================================")

    print("URL:", frame.url)

    print("Participantes encontrados:", total)

    print(
        "Eventos SouthAmericaEvent:",
        await frame.locator(
            '[class*="SouthAmericaEvent"]'
        ).count()
    )

    print(
        "Fechas event-time:",
        await frame.locator(
            '[data-component="event-time"]'
        ).count()
    )

    print(
        "Fechas start-date:",
        await frame.locator(
            '[data-part="start-date"]'
        ).count()
    )

    print(
        "Indicadores en vivo:",
        await frame.locator(
            '[data-component="live-badge"]'
        ).count()
    )

    resultados = []

    limite = min(total, MAX_PARTICIPANTES)

    for i in range(limite):

        participante = participantes.nth(i)

        try:

            datos = await diagnosticar_participante(
                participante,
                i
            )

            resultados.append(datos)

            print(
                f"\nParticipante {i}: "
                f"{datos['participante']}"
            )

            for ancestro in datos["ancestros"]:

                print(
                    f"  Ancestro nivel "
                    f"{ancestro['nivel']}: "
                    f"{ancestro['etiqueta']}"
                )

                print(
                    "    Participantes:",
                    ancestro["participantes"]
                )

                print(
                    "    Fechas:",
                    ancestro["fechas"]
                )

                print(
                    "    En vivo:",
                    ancestro["indicadores_live"]
                )

        except Exception as error:

            print(
                f"Error diagnosticando "
                f"participante {i}: {error}"
            )

    # Guardar toda la información para analizarla.

    with open(
        ARCHIVO_DIAGNOSTICO,
        "w",
        encoding="utf-8"
    ) as archivo:

        json.dump(
            resultados,
            archivo,
            ensure_ascii=False,
            indent=2
        )

    print("\n======================================")
    print("DIAGNOSTICO FINALIZADO")
    print("======================================")

    print("Participantes analizados:", len(resultados))

    print(
        "Archivo generado:",
        Path(ARCHIVO_DIAGNOSTICO).resolve()
    )


# ============================================================
# MAIN
# ============================================================

async def main():

    browser = BrowserManager()

    try:

        await browser.start()

        page = await browser.open_page(
            "apuesta_total",
            URL
        )

        print("Navegador iniciado correctamente.")

        print("Esperando carga del contenido deportivo...")

        await page.wait_for_timeout(15000)

        frame = find_sports_frame(page)

        if frame is None:

            print("\nNo se encontró el iframe deportivo.")

            print("\nFrames disponibles:")

            for current_frame in page.frames:
                print(current_frame.url)

            return

        print("\nIframe deportivo encontrado.")

        await diagnosticar_frame(frame)

        print("\nEl navegador permanecerá abierto 10 segundos.")

        await asyncio.sleep(10)

    except Exception as error:

        print("\nERROR GENERAL:", error)

        raise

    finally:

        await browser.close()


if __name__ == "__main__":

    asyncio.run(main())
