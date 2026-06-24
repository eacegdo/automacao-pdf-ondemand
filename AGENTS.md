---
name: eace-report
description: Executa o robô de automação EACE — faz login na intranet, abre o Status Report e salva como PDF local. Use quando o usuário pedir para rodar, testar, debugar ou modificar o robô EACE, baixar o relatório PDF, ou entender o fluxo de automação da intranet.
---

# EACE Report Automation

Robô Playwright que faz login na intranet EACE, abre o Status Report e salva como PDF.

## Arquivos do robô

- `app/scraper/eace_report.py` — lógica principal (login → popup → PDF)
- `eace_cli.py` — entry point CLI

## Rodar

```bash
python3 eace_cli.py               # headless
python3 eace_cli.py --show-browser  # browser visível (debug)
```

PDF salvo em `output/status_report_<timestamp>.pdf`.

## Fluxo mapeado

1. `GET /version-live/login` — inputs `type=email` + `type=password`, botão "Log In"
2. Login OK → redireciona para `/version-live/intranet`
3. `GET /version-live/np_report_new` — página principal de relatórios
4. Clica hamburguer (≡) — `div.clickable-element` primeiro elemento, x=33 y=67
5. Menu expande → seção "RELATÓRIOS" com itens: Simet, OCE, Telebras, **Status report**
6. Clica "Status report" → popup abre com iframe (`src=javascript:window["contents"]`)
7. Aguarda `button.btn-print` dentro de `page.frames[1]` (confirma conteúdo carregado)
8. Extrai HTML do iframe via `frame.content()`
9. Abre página limpa, injeta HTML, chama `page.pdf()` — evita overlay Bubble.io

## Armadilhas conhecidas

- `page.pdf()` na página principal captura overlay Bubble.io → PDF vazio. **Sempre usar iframe isolado.**
- `page.frames[1]` é o iframe do popup. Se abrir outros iframes antes, índice pode mudar — usar `wait_for_selector("button.btn-print")` no frame certo.
- Hamburguer não tem texto nem aria-label — localizar por `div.clickable-element` first (x=14, y=67).
- `wait_until="networkidle"` no login dá timeout — usar `domcontentloaded` + `wait_for_timeout(3000)`.
- Google weather robot também neste projeto: `python3 cli.py "São Vicente"` — seletores `#wob_*`.

## Credenciais

Ficam em `.env` (não commitado):

```
EACE_EMAIL=seu@email.com
EACE_PASSWORD=suasenha
```
