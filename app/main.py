import logging
import os
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI
from playwright.async_api import async_playwright

from app.eace import scraper
from app.eace.router import router as eace_router
from app.weather.router import router as weather_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")

logger = logging.getLogger("app")

_BLOCKED_DOMAINS_RE = re.compile("|".join(re.escape(d) for d in scraper.BLOCKED_DOMAINS))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando Chromium persistente...")
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = await browser.new_context(
        locale="pt-BR",
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
    )
    await context.route(_BLOCKED_DOMAINS_RE, lambda route: route.abort())

    app.state.playwright = playwright
    app.state.browser = browser
    app.state.context = context
    app.state.logged_in = False
    logger.info("Chromium pronto.")

    email = os.environ.get("EACE_EMAIL")
    password = os.environ.get("EACE_PASSWORD")
    if email and password:
        try:
            page = await context.new_page()
            await scraper.login(page, email, password)
            await page.close()
            app.state.logged_in = True
            logger.info("Sessão já iniciada no startup — logins subsequentes serão pulados.")
        except Exception:
            logger.exception("Login no startup falhou — será tentado de novo na primeira requisição.")

    yield
    await context.close()
    await browser.close()
    await playwright.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="EACE Automação",
        description="Robô EACE + scraping de clima.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(eace_router)
    app.include_router(weather_router)
    return app


app = create_app()
