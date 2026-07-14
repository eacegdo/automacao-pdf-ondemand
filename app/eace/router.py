import asyncio
import logging
import os
import time
from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import Response

from app.eace.scraper import (
    EaceLoginError,
    EacePopupError,
    fetch_report_pdf,
    login,
    save_error_screenshot,
)

logger = logging.getLogger("eace.router")

router = APIRouter(prefix="/report", tags=["report"])

_lock = asyncio.Lock()

MAX_LOGIN_ATTEMPTS = 2
LOGIN_RETRY_BACKOFF_SECONDS = 5

MAX_REPORT_ATTEMPTS = 3
REPORT_RETRY_BACKOFF_SECONDS = 3


def _check_api_key(x_api_key: str | None):
    api_key = os.environ.get("API_KEY")
    if api_key and x_api_key != api_key:
        raise HTTPException(status_code=401, detail="API key inválida ou ausente")


async def _ensure_logged_in(request: Request, email: str, password: str) -> None:
    if request.app.state.logged_in:
        return

    context = request.app.state.context
    last_error: Exception | None = None
    for attempt in range(1, MAX_LOGIN_ATTEMPTS + 1):
        page = await context.new_page()
        try:
            await login(page, email, password)
            request.app.state.logged_in = True
            await page.close()
            return
        except EaceLoginError as e:
            last_error = e
            await page.close()
            logger.warning(
                "Tentativa de login %d/%d falhou (%s). %s",
                attempt, MAX_LOGIN_ATTEMPTS, e,
                "Tentando novamente..." if attempt < MAX_LOGIN_ATTEMPTS else "Desistindo.",
            )
            if attempt < MAX_LOGIN_ATTEMPTS:
                await asyncio.sleep(LOGIN_RETRY_BACKOFF_SECONDS)
        except Exception as e:
            await page.close()
            raise HTTPException(status_code=502, detail=str(e))

    raise HTTPException(status_code=502, detail=str(last_error))


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
        context = request.app.state.context
        await _ensure_logged_in(request, email, password)

        last_error: Exception | None = None
        pdf_bytes: bytes | None = None
        session_relogged = False

        for attempt in range(1, MAX_REPORT_ATTEMPTS + 1):
            page = await context.new_page()
            try:
                pdf_bytes = await fetch_report_pdf(context, page)
                await page.close()
                break
            except EaceLoginError as e:
                await page.close()
                last_error = e
                if session_relogged:
                    # Já tentou relogar uma vez e sessão caiu de novo — para de insistir.
                    raise HTTPException(status_code=502, detail=str(e))
                logger.warning("Sessão expirou em pleno uso (%s). Relogando...", e)
                request.app.state.logged_in = False
                session_relogged = True
                await _ensure_logged_in(request, email, password)
            except EacePopupError as e:
                last_error = e
                logger.warning(
                    "Tentativa %d/%d de buscar o report falhou (%s). %s",
                    attempt, MAX_REPORT_ATTEMPTS, e,
                    "Tentando novamente..." if attempt < MAX_REPORT_ATTEMPTS else "Desistindo.",
                )
                if attempt < MAX_REPORT_ATTEMPTS:
                    await page.close()
                    await asyncio.sleep(REPORT_RETRY_BACKOFF_SECONDS)
                else:
                    await save_error_screenshot(page, "report")
                    await page.close()
            except Exception as e:
                logger.exception("Falha na automação do Status Report")
                await page.close()
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
