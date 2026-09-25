import logging
import os
import re
import time
from datetime import datetime

from playwright.async_api import BrowserContext, Page

LOGIN_URL = "https://eace.org.br/version-live/login"
REPORT_URL = "https://eace.org.br/status_report"

OUTPUT_DIR = "output"

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

logger = logging.getLogger("eace.scraper")

# Texto que só existe quando o dashboard terminou de renderizar.
READY_TEXT = "Dashboard de Escolas Conectadas"

# Quanto esperamos imagens/fontes terminarem antes de imprimir. Se estourar,
# imprimimos assim mesmo — melhor um PDF com uma imagem faltando do que um timeout.
SETTLE_TIMEOUT_MS = 5_000


async def _settle(page: Page) -> None:
    """Espera imagens e fontes, com teto. Substitui o antigo networkidle+sleep fixo."""
    try:
        await page.wait_for_function(
            "() => Array.from(document.images).every(img => img.complete)",
            timeout=SETTLE_TIMEOUT_MS,
        )
    except Exception:
        logger.warning("PDF: imagens não carregaram em %ds, gerando assim mesmo", SETTLE_TIMEOUT_MS // 1000)
    try:
        await page.evaluate("() => document.fonts ? document.fonts.ready : null")
    except Exception:
        pass


async def save_error_screenshot(page: Page, step: str) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(OUTPUT_DIR, f"erro_{step}_{ts}.png")
    try:
        await page.screenshot(path=path, full_page=True)
        logger.error("Print da tela do erro: %s", path)
    except Exception:
        logger.warning("Não deu para salvar o print da tela do erro")


class EaceLoginError(Exception):
    pass


class EacePopupError(Exception):
    pass


async def login(page: Page, email: str, password: str) -> None:
    started = time.monotonic()
    try:
        logger.info("Login: abrindo página")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
        email_input = page.locator("input[type='email']")
        await email_input.wait_for(state="visible", timeout=10_000)
        await email_input.fill(email)
        await page.locator("input[type='password']").fill(password)
        logger.info("Login: enviando e-mail e senha")
        await page.locator("button:has-text('Log In')").click()

        try:
            await page.wait_for_url("**/intranet**", timeout=20_000)
        except Exception:
            raise EaceLoginError("Login falhou — não redirecionou para /intranet. Verifique credenciais.")
        logger.info("Login: OK (%.1fs)", time.monotonic() - started)
    except EaceLoginError as e:
        logger.error("Login: %s", e)
        await save_error_screenshot(page, "login")
        raise
    except Exception:
        logger.exception("Login: erro inesperado")
        await save_error_screenshot(page, "login")
        raise


async def verify_session(context: BrowserContext) -> bool:
    """Checa, sem gerar PDF, se a sessão ainda está logada. Usado pelo watchdog periódico."""
    page = await context.new_page()
    try:
        await page.goto(REPORT_URL, wait_until="domcontentloaded", timeout=30_000)
        return "/login" not in page.url and "status_report" in page.url
    finally:
        await page.close()


def _numero(text: str, pattern: str) -> int:
    match = re.search(pattern, text)
    return int(match.group(1)) if match else 0


def _dados_na_tela(text: str) -> bool:
    """Totais históricos e pelo menos um indicador do dia, da semana ou do mês."""
    if _numero(text, r"TOTAL DE ESCOLAS CONECTADAS\s+(\d+)") <= 0:
        return False
    return any(
        _numero(text, pattern) > 0
        for pattern in (
            r"ESCOLAS CONECTADAS NA DATA\s+\+?\s*(\d+)",
            r"Total da semana:\s*(\d+)",
            r"REALIZADO DO MÊS\s+(\d+)",
        )
    )


async def _esperar_dados(page: Page) -> None:
    """Abre, espera 5s e só segue se os números já estiverem na tela."""
    logger.info("Report: página aberta, esperando 5s pelos dados")
    await page.wait_for_timeout(5_000)
    texto = await page.inner_text("body")
    if READY_TEXT not in texto or not _dados_na_tela(texto):
        raise EacePopupError("dados do Status Report não apareceram em 5s")
    logger.info("Report: dados na tela")


async def _esconder_botao_imprimir(page: Page) -> None:
    """O botão é da tela, não do relatório. Some só no PDF."""
    await page.evaluate(
        """() => {
          for (const el of document.querySelectorAll("button, a, div, span")) {
            if (el.childElementCount > 3) continue;
            const t = (el.innerText || "").replace(/\\s+/g, " ").trim();
            if (t === "Imprimir / PDF") el.style.display = "none";
          }
        }"""
    )


async def fetch_report_pdf(context: BrowserContext, page: Page) -> bytes:
    """Abre https://eace.org.br/status_report (sessão já logada) e gera o PDF.

    A página do Bubble já é o dashboard. Não tem menu lateral nem iframe.
    """
    try:
        logger.info("Report: abrindo /status_report")
        await page.goto(REPORT_URL, wait_until="domcontentloaded", timeout=30_000)
        if "/login" in page.url:
            raise EaceLoginError("sessão expirou, caiu na tela de login")
        await _esperar_dados(page)

        started = time.monotonic()
        logger.info("PDF: gerando")
        await _settle(page)
        await _esconder_botao_imprimir(page)
        box = await page.evaluate(
            """() => ({
              h: Math.max(document.documentElement.scrollHeight, document.body.scrollHeight),
              w: Math.max(document.documentElement.scrollWidth, 1280),
            })"""
        )
        pdf_bytes = await page.pdf(
            print_background=True,
            width=f"{box['w']}px",
            height=f"{box['h']}px",
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
        )

        logger.info("PDF: pronto (%d KB, %.1fs)", len(pdf_bytes) // 1024, time.monotonic() - started)
        return pdf_bytes
    except (EaceLoginError, EacePopupError):
        raise
    except Exception:
        logger.exception("Report: erro inesperado")
        await save_error_screenshot(page, "gerar_pdf")
        raise


async def run_report(context: BrowserContext, email: str, password: str) -> bytes:
    """Login + PDF. Usado pelo CLI. A API loga uma vez e chama fetch_report_pdf."""
    page = await context.new_page()
    try:
        await login(page, email, password)
        return await fetch_report_pdf(context, page)
    finally:
        await page.close()
