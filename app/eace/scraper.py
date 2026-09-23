import logging
import os
import re
import time
from contextlib import asynccontextmanager
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
        return "/login" not in page.url and "status_report" in page.url
    finally:
        await page.close()


def _totais_carregados(text: str) -> bool:
    match = re.search(r"TOTAL DE ESCOLAS CONECTADAS\s+(\d+)", text)
    return bool(match and int(match.group(1)) > 0)


async def _esperar_dados(page: Page) -> None:
    """O Bubble pinta o layout com zeros e preenche em duas levas.

    Primeiro os totais históricos, depois o dia/semana e o gráfico. Imprimir
    no meio gera PDF com +0. Espera o texto parar de mudar depois que o total
    histórico já entrou.
    """
    deadline = time.monotonic() + 25
    anterior = None
    estavel = 0
    while time.monotonic() < deadline:
        texto = await page.inner_text("body")
        if _totais_carregados(texto) and texto == anterior:
            estavel += 1
            if estavel >= 3:
                return
        else:
            estavel = 0
            anterior = texto
        await page.wait_for_timeout(500)
    raise EacePopupError("Números do Status Report não estabilizaram a tempo.")


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
        async with _step("abrir status_report"):
            await page.goto(REPORT_URL, wait_until="domcontentloaded", timeout=30_000)
            if "/login" in page.url:
                raise EaceLoginError("Sessão expirou — redirecionado para tela de login.")
            try:
                await page.get_by_text(READY_TEXT).first.wait_for(state="visible", timeout=20_000)
                await _esperar_dados(page)
            except EacePopupError:
                raise
            except Exception:
                raise EacePopupError("Status Report não apareceu em /status_report.")

        async with _step("gerar PDF"):
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

        logger.info("PDF gerado com sucesso (%d bytes).", len(pdf_bytes))
        return pdf_bytes
    except (EaceLoginError, EacePopupError):
        raise
    except Exception:
        logger.exception("Erro inesperado ao gerar o report")
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
