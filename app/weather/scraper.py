from playwright.async_api import BrowserContext

SEARCH_URL = "https://www.google.com/search?q={query}&hl=pt-BR&gl=BR"

# IDs do widget de clima do Google — estáveis pois alimentam o JS de toggle de unidades
SELECTORS = {
    "temperature":   "#wob_tm",
    "condition":     "#wob_dc",
    "humidity":      "#wob_hm",
    "wind":          "#wob_ws",
    "precipitation": "#wob_pp",
    "datetime":      "#wob_dts",
}

FALLBACK_SELECTORS = {
    "widget_root": "div[data-attrid='kc:/location/location:weather']",
}


class ScraperError(Exception):
    pass


async def scrape_weather(context: BrowserContext, query: str) -> dict:
    page = await context.new_page()
    url = SEARCH_URL.format(query=query.replace(" ", "+"))

    await page.goto(url, wait_until="domcontentloaded")

    widget_found = False
    try:
        await page.wait_for_selector("#wob_tm", timeout=8_000)
        widget_found = True
    except Exception:
        try:
            await page.wait_for_selector(FALLBACK_SELECTORS["widget_root"], timeout=3_000)
            widget_found = True
        except Exception:
            pass

    if not widget_found:
        await page.close()
        raise TimeoutError(
            f"Widget de clima não encontrado para '{query}'. "
            "Google pode ter retornado página de desambiguação ou bloqueado o acesso."
        )

    raw: dict = {}
    for key, selector in SELECTORS.items():
        el = page.locator(selector)
        count = await el.count()
        raw[key] = (await el.inner_text()).strip() if count > 0 else None

    await page.close()
    return raw
