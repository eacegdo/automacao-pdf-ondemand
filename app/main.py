import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from playwright.async_api import async_playwright

from app.eace.router import router as eace_router
from app.weather.router import router as weather_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")

logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando Chromium persistente...")
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
    )
    app.state.playwright = playwright
    app.state.browser = browser
    logger.info("Chromium pronto.")
    yield
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
