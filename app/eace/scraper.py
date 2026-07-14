import logging
import os
from datetime import datetime

from playwright.async_api import BrowserContext, Page

LOGIN_URL  = "https://eace.org.br/version-live/login"
REPORT_URL = "https://eace.org.br/version-live/np_report_new"

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


async def save_error_screenshot(page: Page, step: str) -> None:
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


async def login(page: Page, email: str, password: str) -> None:
    try:
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
    except Exception:
        logger.exception("Erro na etapa 'login'")
        await save_error_screenshot(page, "login")
        raise


async def verify_session(context: BrowserContext) -> bool:
    """Checa, sem gerar PDF, se a sessão ainda está logada. Usado pelo watchdog periódico."""
    page = await context.new_page()
    try:
        await page.goto(REPORT_URL, wait_until="domcontentloaded", timeout=30_000)
        return "/login" not in page.url
    finally:
        await page.close()


async def fetch_report_pdf(context: BrowserContext, page: Page) -> bytes:
    """Navega até o Status Report (sessão já logada) e gera o PDF.

    Página é criada e fechada por request — não fica aba viva em repouso.
    """
    try:
        logger.info("Navegando até o Status Report...")
        await page.goto(REPORT_URL, wait_until="domcontentloaded", timeout=30_000)

        if "/login" in page.url:
            raise EaceLoginError("Sessão expirou — redirecionado para tela de login.")

        # --- ABRE MENU LATERAL ---
        logger.info("Abrindo menu lateral...")
        hamburger = page.locator("div.clickable-element").first
        try:
            await hamburger.wait_for(state="visible", timeout=10_000)
            await hamburger.click(force=True)
        except EaceLoginError:
            raise
        except Exception:
            raise EacePopupError("Menu lateral não apareceu/não foi possível clicar.")

        # --- CLICA "Status report" ---
        logger.info("Clicando em 'Status report'...")
        sr = page.get_by_text("Status report").first
        try:
            await sr.wait_for(state="visible", timeout=8_000)
            await sr.click()
        except Exception:
            raise EacePopupError("Opção 'Status report' não apareceu/não foi possível clicar.")

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
    except (EaceLoginError, EacePopupError):
        raise
    except Exception:
        logger.exception("Erro inesperado ao gerar o report")
        await save_error_screenshot(page, "gerar_pdf")
        raise
