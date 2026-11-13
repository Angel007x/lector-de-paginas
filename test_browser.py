
import asyncio

from browser_manager import BrowserManager


async def main():

    browser = BrowserManager()

    try:

        await browser.start()

        page = await browser.open_page(
            "prueba",
            "https://example.com"
        )

        print("Navegador iniciado correctamente")
        print("Título:", await page.title())

        await page.wait_for_timeout(5000)

    finally:

        await browser.close()


asyncio.run(main())
