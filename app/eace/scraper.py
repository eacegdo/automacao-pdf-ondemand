import logging
import os
from datetime import datetime

from playwright.async_api import BrowserContext, Page

LOGIN_URL  = "https://eace.org.br/version-live/login"
REPORT_URL = "https://eace.org.br/version-live/np_report_new"

OUTPUT_DIR = "output"

MAX_REPORT_ATTEMPTS = 3
REPORT_RETRY_BACKOFF_SECONDS = 3_000

logger = logging.getLogger("eace.scraper")


async def _save_error_screenshot(page: Page, step: str) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(OUTPUT_DIR, f"erro_{step}_{ts}.png")
    try:
        await page.screenshot(path=path, full_page=True)
        logger.error("Screenshot do erro salvo em %s", path)
    except Exception:
        logger.exception("Não foi possível salvar screenshot do erro")


class EaceLoginError(Exception):
    pass


class EacePopupError(Exception):
    pass


async def _login(page: Page, email: str, password: str) -> None:
    logger.info("Abrindo página de login...")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    email_input = page.locator("input[type='email']")
    await email_input.wait_for(state="visible", timeout=10_000)
    await email_input.fill(email)
    await page.locator("input[type='password']").fill(password)
    logger.info("Enviando credenciais...")
    await page.locator("button:has-text('Log In')").click()

    try:
        await page.wait_for_url("**/intranet**", timeout=20_000)
    except Exception:
        raise EaceLoginError("Login falhou — não redirecionou para /intranet. Verifique credenciais.")
    logger.info("Login OK.")


async def _fetch_report_pdf(context: BrowserContext, page: Page) -> bytes:
    logger.info("Navegando até o Status Report...")
    await page.goto(REPORT_URL, wait_until="domcontentloaded", timeout=30_000)

    # --- ABRE MENU LATERAL ---
    logger.info("Abrindo menu lateral...")
    hamburger = page.locator("div.clickable-element").first
    await hamburger.wait_for(state="visible", timeout=10_000)
    await hamburger.click(force=True)

    # --- CLICA "Status report" ---
    logger.info("Clicando em 'Status report'...")
    sr = page.get_by_text("Status report").first
    await sr.wait_for(state="visible", timeout=8_000)
    await sr.click()

    # --- AGUARDA IFRAME ---
    logger.info("Aguardando iframe do relatório...")
    iframe = page.locator("iframe").first
    try:
        await iframe.wait_for(state="visible", timeout=15_000)
    except Exception:
        raise EacePopupError("Iframe do Status Report não apareceu.")

    report_frame = page.frames[1]
    try:
        await report_frame.wait_for_selector("button.btn-print", timeout=20_000)
    except Exception:
        raise EacePopupError("Conteúdo do Status Report não carregou no iframe.")
    logger.info("Conteúdo do relatório carregado.")

    # Margem extra para gráficos/imagens renderizarem
    await page.wait_for_timeout(1_000)

    # --- EXTRAI HTML DO IFRAME E GERA PDF EM PÁGINA LIMPA ---
    # page.pdf() captura overlay Bubble.io — precisa do iframe isolado
    logger.info("Extraindo HTML e gerando PDF...")
    report_html = await report_frame.content()

    pdf_page = await context.new_page()
    try:
        await pdf_page.set_content(report_html, wait_until="networkidle")
        await pdf_page.wait_for_timeout(1_000)
        pdf_bytes = await pdf_page.pdf(format="A4", print_background=True)
    finally:
        await pdf_page.close()

    logger.info("PDF gerado com sucesso (%d bytes).", len(pdf_bytes))
    return pdf_bytes


async def run_report(context: BrowserContext, email: str, password: str) -> bytes:
    page = await context.new_page()

    try:
        await _login(page, email, password)
    except Exception:
        logger.exception("Erro na etapa 'login'")
        await _save_error_screenshot(page, "login")
        raise

    # Login já validado — se o report falhar, tenta de novo na MESMA página/sessão,
    # sem refazer login.
    last_error: Exception | None = None
    for attempt in range(1, MAX_REPORT_ATTEMPTS + 1):
        try:
            pdf_bytes = await _fetch_report_pdf(context, page)
            await page.close()
            return pdf_bytes
        except EacePopupError as e:
            last_error = e
            logger.warning(
                "Tentativa %d/%d de buscar o report falhou (%s). %s",
                attempt, MAX_REPORT_ATTEMPTS, e,
                "Tentando novamente..." if attempt < MAX_REPORT_ATTEMPTS else "Desistindo.",
            )
            if attempt < MAX_REPORT_ATTEMPTS:
                await page.wait_for_timeout(REPORT_RETRY_BACKOFF_SECONDS)
            else:
                await _save_error_screenshot(page, "report")
        except Exception:
            logger.exception("Erro inesperado ao gerar o report")
            await _save_error_screenshot(page, "gerar_pdf")
            raise

    raise last_error
