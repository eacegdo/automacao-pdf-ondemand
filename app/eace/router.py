import asyncio
import os
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from playwright.async_api import async_playwright

from app.eace.scraper import run_report

router = APIRouter(prefix="/report", tags=["report"])

_lock = asyncio.Lock()


@router.post("/run-report")
async def run_report_endpoint():
    email = os.environ.get("EACE_EMAIL")
    password = os.environ.get("EACE_PASSWORD")
    if not email or not password:
        raise HTTPException(status_code=500, detail="EACE_EMAIL ou EACE_PASSWORD não configurados")

    if _lock.locked():
        raise HTTPException(status_code=429, detail="Robô já em execução. Tente em instantes.")

    async with _lock:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
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
                try:
                    pdf_bytes = await run_report(context, email, password)
                finally:
                    await browser.close()
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))

    filename = f"status_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
