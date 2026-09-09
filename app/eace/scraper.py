import logging
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime

from playwright.async_api import BrowserContext, Frame, Page

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

# URL do iframe do Status Report, descoberta na primeira execução. Depois disso
# vamos direto nela e pulamos o boot do app Bubble + menu lateral.
_report_frame_url: str | None = None

# Quanto esperamos imagens/fontes terminarem antes de imprimir. Se estourar,
# imprimimos assim mesmo — melhor um PDF com uma imagem faltando do que um timeout.
SETTLE_TIMEOUT_MS = 5_000


@asynccontextmanager
async def _step(name: str):
    """Loga quanto cada etapa levou. É assim que a gente descobre onde o tempo vai."""
    started = time.monotonic()
    try:
        yield
    finally:
        logger.info("[timing] %s: %.1fs", name, time.monotonic() - started)


async def _settle(page: Page) -> None:
    """Espera imagens e fontes, com teto. Substitui o antigo networkidle+sleep fixo."""
    try:
        await page.wait_for_function(
            "() => Array.from(document.images).every(img => img.complete)",
            timeout=SETTLE_TIMEOUT_MS,
        )
    except Exception:
        logger.warning("Imagens não terminaram em %dms — imprimindo assim mesmo.", SETTLE_TIMEOUT_MS)
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


async def _pdf_direto(context: BrowserContext, url: str) -> bytes | None:
    """Abre a URL do iframe direto e imprime. Pula o boot do Bubble e o menu.

    Devolve None se a página não for o report esperado — aí o chamador cai no
    caminho longo. Nunca levanta EacePopupError: falhar aqui não é erro, é fallback.
    """
    pdf_page = await context.new_page()
    try:
        await pdf_page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        if "/login" in pdf_page.url:
            raise EaceLoginError("Sessão expirou — redirecionado para tela de login.")
        try:
            await pdf_page.wait_for_selector("button.btn-print", timeout=15_000)
        except Exception:
            logger.info("URL direta não renderizou o report; caindo no caminho longo.")
            return None
        await _settle(pdf_page)
        return await pdf_page.pdf(format="A4", print_background=True)
    finally:
        await pdf_page.close()


async def _abrir_report_frame(page: Page) -> Frame:
    """Caminho longo: home -> menu lateral -> Status report -> iframe carregado."""
    async with _step("goto home"):
        await page.goto(REPORT_URL, wait_until="domcontentloaded", timeout=30_000)

    if "/login" in page.url:
        raise EaceLoginError("Sessão expirou — redirecionado para tela de login.")

    async with _step("menu lateral"):
        hamburger = page.locator("div.clickable-element").first
        try:
            await hamburger.wait_for(state="visible", timeout=10_000)
            await hamburger.click(force=True)
        except Exception:
            raise EacePopupError("Menu lateral não apareceu/não foi possível clicar.")

    async with _step("click Status report"):
        sr = page.get_by_text("Status report").first
        try:
            await sr.wait_for(state="visible", timeout=8_000)
            await sr.click()
        except Exception:
            raise EacePopupError("Opção 'Status report' não apareceu/não foi possível clicar.")

    async with _step("iframe visível"):
        try:
            await page.locator("iframe").first.wait_for(state="visible", timeout=15_000)
        except Exception:
            raise EacePopupError("Iframe do Status Report não apareceu.")

    report_frame = page.frames[1]
    async with _step("conteúdo do iframe"):
        try:
            await report_frame.wait_for_selector("button.btn-print", timeout=20_000)
        except Exception:
            raise EacePopupError("Conteúdo do Status Report não carregou no iframe.")

    return report_frame


async def fetch_report_pdf(context: BrowserContext, page: Page) -> bytes:
    """Navega até o Status Report (sessão já logada) e gera o PDF.

    Página é criada e fechada por request — não fica aba viva em repouso.
    """
    global _report_frame_url

    try:
        if _report_frame_url:
            async with _step("caminho rápido (URL direta)"):
                pdf_bytes = await _pdf_direto(context, _report_frame_url)
            if pdf_bytes is not None:
                logger.info("PDF gerado pelo caminho rápido (%d bytes).", len(pdf_bytes))
                return pdf_bytes
            _report_frame_url = None

        report_frame = await _abrir_report_frame(page)

        # Guarda pra próxima chamada ir direto.
        if report_frame.url and report_frame.url != "about:blank":
            _report_frame_url = report_frame.url
            logger.info("URL do report cacheada: %s", _report_frame_url)

        # --- EXTRAI HTML DO IFRAME E GERA PDF EM PÁGINA LIMPA ---
        # page.pdf() captura overlay Bubble.io — precisa do iframe isolado
        async with _step("extrair HTML + gerar PDF"):
            report_html = await report_frame.content()

            # Sem <base>, todo caminho relativo do report resolve contra about:blank
            # e o recurso morre — o que fazia o antigo networkidle esperar à toa.
            if report_frame.url:
                base_tag = f'<base href="{report_frame.url}">'
                report_html, n = re.subn(
                    r"<head[^>]*>", lambda m: m.group(0) + base_tag, report_html, count=1
                )
                if not n:
                    report_html = base_tag + report_html

            pdf_page = await context.new_page()
            try:
                await pdf_page.set_content(report_html, wait_until="load")
                await _settle(pdf_page)
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
