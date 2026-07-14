import asyncio
import logging
import os
import re
import time
from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import Response

from app.eace.scraper import EaceLoginError, EacePopupError, run_report

logger = logging.getLogger("eace.router")

router = APIRouter(prefix="/report", tags=["report"])

BLOCKED_DOMAINS = (
    "google-analytics.com",
    "googletagmanager.com",
    "doubleclick.net",
    "facebook.net",
    "connect.facebook.net",
    "hotjar.com",
    "intercom.io",
    "widget.intercom.io",
    "segment.com",
    "sentry.io",
)

_lock = asyncio.Lock()

# Retry aqui é só pra falha de LOGIN (contexto novo, sem sessão pra perder).
# Retry de report (sessão já logada) é tratado dentro de run_report, reusando a página.
MAX_LOGIN_ATTEMPTS = 2
LOGIN_RETRY_BACKOFF_SECONDS = 5


def _check_api_key(x_api_key: str | None):
    api_key = os.environ.get("API_KEY")
    if api_key and x_api_key != api_key:
        raise HTTPException(status_code=401, detail="API key inválida ou ausente")


@router.post("/run-report")
async def run_report_endpoint(request: Request, x_api_key: str | None = Header(default=None)):
    _check_api_key(x_api_key)
    email = os.environ.get("EACE_EMAIL")
    password = os.environ.get("EACE_PASSWORD")
    if not email or not password:
        raise HTTPException(status_code=500, detail="EACE_EMAIL ou EACE_PASSWORD não configurados")

    if _lock.locked():
        raise HTTPException(status_code=429, detail="Robô já em execução. Tente em instantes.")

    start_time = time.monotonic()

    async with _lock:
        last_error: Exception | None = None
        pdf_bytes: bytes | None = None
        for attempt in range(1, MAX_LOGIN_ATTEMPTS + 1):
            try:
                browser = request.app.state.browser
                context = await browser.new_context(
                    locale="pt-BR",
                    viewport={"width": 1280, "height": 900},
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0.0.0 Safari/537.36"
                    ),
                )
                await context.route(
                    re.compile("|".join(re.escape(d) for d in BLOCKED_DOMAINS)),
                    lambda route: route.abort(),
                )
                try:
                    pdf_bytes = await run_report(context, email, password)
                finally:
                    await context.close()
                break
            except EaceLoginError as e:
                last_error = e
                logger.warning(
                    "Tentativa de login %d/%d falhou (%s). %s",
                    attempt, MAX_LOGIN_ATTEMPTS, e,
                    "Tentando novamente..." if attempt < MAX_LOGIN_ATTEMPTS else "Desistindo.",
                )
                if attempt < MAX_LOGIN_ATTEMPTS:
                    await asyncio.sleep(LOGIN_RETRY_BACKOFF_SECONDS)
            except EacePopupError as e:
                raise HTTPException(status_code=502, detail=str(e))
            except Exception as e:
                logger.exception("Falha na automação do Status Report")
                raise HTTPException(status_code=502, detail=str(e))

        if pdf_bytes is None:
            raise HTTPException(status_code=502, detail=str(last_error))

    elapsed = time.monotonic() - start_time
    logger.info("Relatório gerado em %.1fs.", elapsed)

    filename = f"status_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "X-Generation-Time-Seconds": f"{elapsed:.1f}",
        },
    )
