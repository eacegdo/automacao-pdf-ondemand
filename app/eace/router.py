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
    login,
    open_report_page,
    render_report_pdf,
)

logger = logging.getLogger("eace.router")

router = APIRouter(prefix="/report", tags=["report"])

_lock = asyncio.Lock()

MAX_LOGIN_ATTEMPTS = 2
LOGIN_RETRY_BACKOFF_SECONDS = 5

MAX_REOPEN_ATTEMPTS = 2


def _check_api_key(x_api_key: str | None):
    api_key = os.environ.get("API_KEY")
    if api_key and x_api_key != api_key:
        raise HTTPException(status_code=401, detail="API key inválida ou ausente")


async def _ensure_logged_in(request: Request, email: str, password: str, page) -> None:
    if request.app.state.logged_in:
        return

    last_error: Exception | None = None
    for attempt in range(1, MAX_LOGIN_ATTEMPTS + 1):
        try:
            await login(page, email, password)
            request.app.state.logged_in = True
            return
        except EaceLoginError as e:
            last_error = e
            logger.warning(
                "Tentativa de login %d/%d falhou (%s). %s",
                attempt, MAX_LOGIN_ATTEMPTS, e,
                "Tentando novamente..." if attempt < MAX_LOGIN_ATTEMPTS else "Desistindo.",
            )
            if attempt < MAX_LOGIN_ATTEMPTS:
                await asyncio.sleep(LOGIN_RETRY_BACKOFF_SECONDS)
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))

    raise HTTPException(status_code=502, detail=str(last_error))


async def _ensure_report_open(request: Request, email: str, password: str) -> None:
    context = request.app.state.context

    if request.app.state.report_ready:
        return

    if request.app.state.report_page is not None:
        try:
            await request.app.state.report_page.close()
        except Exception:
            pass

    page = await context.new_page()
    request.app.state.report_page = page

    await _ensure_logged_in(request, email, password, page)

    try:
        await open_report_page(page)
        request.app.state.report_ready = True
    except EaceLoginError:
        request.app.state.logged_in = False
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


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
        last_error: Exception | None = None
        pdf_bytes: bytes | None = None

        for attempt in range(1, MAX_REOPEN_ATTEMPTS + 1):
            try:
                await _ensure_report_open(request, email, password)
                pdf_bytes = await render_report_pdf(context, request.app.state.report_page)
                break
            except (EaceLoginError, EacePopupError) as e:
                last_error = e
                request.app.state.report_ready = False
                logger.warning(
                    "Report indisponível na tentativa %d/%d (%s). %s",
                    attempt, MAX_REOPEN_ATTEMPTS, e,
                    "Reabrindo..." if attempt < MAX_REOPEN_ATTEMPTS else "Desistindo.",
                )
            except HTTPException:
                raise
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
