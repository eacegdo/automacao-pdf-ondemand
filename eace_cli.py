#!/usr/bin/env python3
"""
Robô EACE: login → /status_report → gera PDF → salva localmente.
"""
import asyncio
import argparse
import logging
import os
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright

from app.core.logs import setup_logging
from app.eace.scraper import run_report

setup_logging()
logger = logging.getLogger("eace.cli")

load_dotenv()
EMAIL    = os.environ["EACE_EMAIL"]
PASSWORD = os.environ["EACE_PASSWORD"]


def parse_args():
    p = argparse.ArgumentParser(description="Baixa Status Report PDF da intranet EACE.")
    p.add_argument("--show-browser", action="store_true", help="Abre browser visível")
    return p.parse_args()


async def main():
    args = parse_args()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not args.show_browser,
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

        started = time.monotonic()
        logger.info("▶ Robô chamado (CLI%s)", ", browser visível" if args.show_browser else "")
        try:
            pdf_bytes = await run_report(context, EMAIL, PASSWORD)
            out = Path("output")
            out.mkdir(exist_ok=True)
            path = out / f"status_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            path.write_bytes(pdf_bytes)
            logger.info("■ Concluído em %.1fs, PDF salvo em %s", time.monotonic() - started, path)
        except Exception as e:
            logger.error("■ Falhou em %.1fs: %s", time.monotonic() - started, e)
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
