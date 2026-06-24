from playwright.async_api import BrowserContext

LOGIN_URL  = "https://eace.org.br/version-live/login"
REPORT_URL = "https://eace.org.br/version-live/np_report_new"


class EaceLoginError(Exception):
    pass


class EacePopupError(Exception):
    pass


async def run_report(context: BrowserContext, email: str, password: str) -> bytes:
    page = await context.new_page()

    # --- LOGIN ---
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_timeout(3_000)
    await page.locator("input[type='email']").fill(email)
    await page.locator("input[type='password']").fill(password)
    await page.locator("button:has-text('Log In')").click()

    try:
        await page.wait_for_url("**/intranet**", timeout=12_000)
    except Exception:
        raise EaceLoginError("Login falhou — não redirecionou para /intranet. Verifique credenciais.")

    # --- NAVEGA PARA REPORT ---
    await page.goto(REPORT_URL, wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_timeout(4_000)

    # --- ABRE MENU LATERAL ---
    hamburger = page.locator("div.clickable-element").first
    await hamburger.click(force=True)
    await page.wait_for_timeout(1_500)

    # --- CLICA "Status report" ---
    sr = page.get_by_text("Status report").first
    await sr.wait_for(state="visible", timeout=8_000)
    await sr.click()
    await page.wait_for_timeout(4_000)

    # --- AGUARDA IFRAME ---
    iframe = page.locator("iframe").first
    try:
        await iframe.wait_for(state="visible", timeout=10_000)
    except Exception:
        raise EacePopupError("Iframe do Status Report não apareceu.")

    report_frame = page.frames[1]
    try:
        await report_frame.wait_for_selector("button.btn-print", timeout=15_000)
    except Exception:
        raise EacePopupError("Conteúdo do Status Report não carregou no iframe.")

    # Margem extra para gráficos/imagens renderizarem
    await page.wait_for_timeout(2_000)

    # --- EXTRAI HTML DO IFRAME E GERA PDF EM PÁGINA LIMPA ---
    # page.pdf() captura overlay Bubble.io — precisa do iframe isolado
    report_html = await report_frame.content()

    pdf_page = await context.new_page()
    await pdf_page.set_content(report_html, wait_until="networkidle")
    await pdf_page.wait_for_timeout(2_000)

    pdf_bytes = await pdf_page.pdf(format="A4", print_background=True)

    await pdf_page.close()
    await page.close()
    return pdf_bytes
