
import asyncio
from time import perf_counter
from urllib.parse import urlsplit

from browser_manager import BrowserManager


# ==========================================
# CONFIGURACION
# ==========================================

URL = "https://www.bet365.pe/"

WAIT_SECONDS = 25

captured_responses = 0
response_tasks = set()


# ==========================================
# MONITOREAR RESPUESTAS
# ==========================================

async def monitor_response(response):

    global captured_responses

    parsed = urlsplit(response.url)

    # Mostrar solamente respuestas de Bet365
    if "bet365" not in parsed.netloc.lower():
        return

    captured_responses += 1

    try:
        headers = await response.all_headers()

        content_type = headers.get(
            "content-type",
            "desconocido"
        )

    except Exception:
        content_type = "desconocido"

    print("\n----------------------------------")

    print("RESPUESTA:", captured_responses)

    print("URL:", response.url[:250])

    print("HTTP:", response.status)

    print("TIPO:", content_type)

    print("----------------------------------")


# ==========================================
# MAIN
# ==========================================

async def main():

    global captured_responses

    browser = BrowserManager()

    start = perf_counter()

    try:

        print("Iniciando Chromium...")

        await browser.start()

        page = await browser.context.new_page()

        browser.pages["bet365"] = page

        # Registrar respuestas antes de navegar
        def schedule_response(response):

            task = asyncio.create_task(
                monitor_response(response)
            )

            response_tasks.add(task)

            task.add_done_callback(
                response_tasks.discard
            )

        page.on("response", schedule_response)

        page.on(
            "requestfailed",
            lambda request: print(
                "\nERROR DE PETICION:",
                request.url[:200],
                request.failure
            )
        )

        print("\nAbriendo Bet365...")

        await page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60000
        )

        print("\nPágina abierta.")

        print("URL actual:", page.url)

        print("\nEsperando carga de contenido...")

        await page.wait_for_timeout(
            WAIT_SECONDS * 1000
        )

        
        # ==========================================
        # PRUEBA DE AVISO DE COOKIES
        # ==========================================

        print("\n========== PRUEBA COOKIES ==========")

        try:

            cookie_button = page.get_by_text(
                "Solo esenciales",
                exact=True
            )

            count = await cookie_button.count()

            print("Botón Solo esenciales:", count)

            if count > 0:

                await cookie_button.first.click(
                    timeout=5000
                )

                print("Se seleccionó Solo esenciales.")

                await page.wait_for_timeout(10000)

            else:

                print("No se encontró el botón.")

        except Exception as error:

            print("Error con cookies:", error)


        
# ==========================================
# PRUEBA: ENTRAR A FUTBOL
# ==========================================

        print("\n========== ENTRANDO A FUTBOL ==========")

        try:

            football = page.get_by_text(
                "Fútbol",
                exact=True
            )

            count = await football.count()

            print("Elementos Fútbol encontrados:", count)

            clicked = False

            for i in range(count):

                element = football.nth(i)

                if await element.is_visible():

                    print("Haciendo clic en Fútbol:", i)

                    await element.click(timeout=5000)

                    clicked = True

                    break

            if clicked:

                print("Esperando carga de fútbol...")

                await page.wait_for_timeout(12000)

            else:

                print("No se encontró un elemento visible de Fútbol.")

        except Exception as error:

            print("Error entrando a fútbol:", error)



        
        print("\n========== DIAGNOSTICO DOM FUTBOL ==========")

        print("URL:", page.url)

        print("Título:", await page.title())

        # Comprobar posibles elementos deportivos
        selectors = [
            "[class*='Fixture']",
            "[class*='Event']",
            "[class*='Participant']",
            "[class*='Market']",
            "[class*='Scoreboard']",
            "[data-testid]"
        ]

        for selector in selectors:

            try:

                locator = page.locator(selector)

                count = await locator.count()

                print(f"{selector}: {count}")

                if count > 0:

                    for i in range(min(count, 3)):

                        try:

                            print(
                                "  ",
                                (await locator.nth(i).inner_text())[:200]
                            )

                        except Exception:
                            pass

            except Exception as error:

                print("Error:", error)


        print("\n========== FRAMES ==========")

        for i, frame in enumerate(page.frames):

            print(
                i,
                frame.url[:250]
            )


        print("\n========== TEXTO FINAL ==========")

        text = await page.locator("body").inner_text()

        print(text[:4000])



        # ==========================================
        # DIAGNOSTICO DE FUTBOL
        # ==========================================

        print("\n========== RESULTADO FUTBOL ==========")

        print("URL:", page.url)

        body_text = await page.locator(
            "body"
        ).inner_text()

        print(body_text[:5000])

        await page.screenshot(
            path="bet365_futbol.png",
            full_page=False
        )

        print("\nCaptura guardada: bet365_futbol.png")




        # ==========================================
        # COMPROBAR PARTIDOS
        # ==========================================

        print("\n========== DESPUES DE COOKIES ==========")

        body_text = await page.locator(
            "body"
        ).inner_text()

        print(body_text[:5000])

        print("\nURL:", page.url)



        # Esperar las tareas de diagnóstico pendientes
        if response_tasks:

            await asyncio.gather(
                *list(response_tasks),
                return_exceptions=True
            )

        print("\n========== DIAGNOSTICO ==========")

        print("Título:", await page.title())

        print("URL final:", page.url)

        print(
            "Respuestas Bet365:",
            captured_responses
        )

        try:

            body_text = await page.locator(
                "body"
            ).inner_text(timeout=10000)

            print("\n========== TEXTO DE LA PAGINA ==========")

            print(body_text[:3000])

        except Exception as error:

            print("No se pudo leer el contenido:", error)

        # Guardar captura visual
        await page.screenshot(
            path="bet365_diagnostico.png",
            full_page=False
        )

        print("\nCaptura guardada:")
        print("bet365_diagnostico.png")

        print(
            "\nTiempo total:",
            round(perf_counter() - start, 2),
            "segundos"
        )

        print("\nDiagnóstico terminado.")

        # Mantener Chromium abierto hasta cerrar manualmente
        input("\nPresiona ENTER para cerrar...")

    except Exception as error:

        print("\nERROR GENERAL:", error)

    finally:

        if response_tasks:

            await asyncio.gather(
                *list(response_tasks),
                return_exceptions=True
            )

        await browser.close()

        print("\nChromium cerrado.")


if __name__ == "__main__":

    asyncio.run(main())
