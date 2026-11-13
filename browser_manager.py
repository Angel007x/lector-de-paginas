
from playwright.async_api import async_playwright


class BrowserManager:

    def __init__(self):

        self.playwright = None
        self.browser = None
        self.context = None
        self.pages = {}

    async def start(self):

        self.playwright = await async_playwright().start()

        self.browser = await self.playwright.chromium.launch(
            headless=False
        )

        self.context = await self.browser.new_context()

        print("Navegador iniciado correctamente")

    async def open_page(self, name, url):

        if self.context is None:
            raise RuntimeError(
                "El navegador no ha sido iniciado."
            )

        page = await self.context.new_page()

        await page.goto(
            url,
            wait_until="domcontentloaded"
        )

        self.pages[name] = page

        print(f"Página abierta: {name}")

        return page

    async def close(self):

        if self.context:

            await self.context.close()
            self.context = None

        if self.browser:

            await self.browser.close()
            self.browser = None

        if self.playwright:

            await self.playwright.stop()
            self.playwright = None

        self.pages.clear()

        print("Navegador cerrado")
