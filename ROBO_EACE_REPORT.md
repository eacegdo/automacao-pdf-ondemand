# Robô: EACE Status Report PDF

## Objetivo

Login em eace.org.br → acessar np_report_new → clicar "Status Report" no menu lateral → popup abre → clicar "Imprimir PDF" → salvar PDF localmente.

---

## URLs

- Login: `https://eace.org.br/version-live/login`
- Target: `https://eace.org.br/version-live/np_report_new`

---

## O que foi mapeado até agora

### Página de login (`/version-live/login`)

- Input `type='email'` placeholder `seuemail@email.com`
- Input `type='password'` placeholder `********`
- Botão `Log In`
- Screenshot: `/tmp/s1_login.png`

### Credenciais

- Email: `wellington.santos@eace.org.br`
- Senha: `@Qwew17082002`

### ⚠️ Problema encontrado

Login em `version-live` **falhou** — após clicar "Log In", URL permaneceu em `/version-live/login` (não redirecionou).

- Possíveis causas: credenciais não funcionam em `version-live`, ou existe validação adicional (2FA, captcha invisível, conta só existe em `version-test`)
- `version-test` com as mesmas credenciais: **não testado ainda**

### Comportamento de redirecionamento

- Acesso direto a `/version-live/np_report_new` sem login → redireciona para home (`/version-live/`)
- Confirma que autenticação é obrigatória antes de navegar

---

## Passos planejados para o robô (pendente confirmação de login)

1. `goto` `/version-live/login`
2. Aguardar `input[type='email']` visível
3. Fechar popup OneSignal se presente (intercepta cliques)
4. Preencher email + senha
5. Clicar `button:has-text('Log In')`
6. Aguardar redirecionamento para `eace.org.br/intranet` (confirma login OK)
7. `goto` `/version-live/np_report_new`
8. Aguardar sidebar carregar
9. Clicar "Status Report" no menu lateral → **seletores a mapear**
10. Aguardar popup abrir → **seletores a mapear**
11. Clicar "Imprimir PDF" → **seletor a mapear**
12. Interceptar download do PDF ou usar `page.pdf()`
13. Salvar em `./output/status_report_<timestamp>.pdf`

---

## Pendências

- [ ] Confirmar se login funciona em `version-live` ou se precisa `version-test`
- [ ] Mapear seletores do menu lateral (sidebar) dentro de `np_report_new`
- [ ] Mapear seletores do popup de Status Report
- [ ] Mapear botão "Imprimir PDF" dentro do popup
- [ ] Definir estratégia de captura do PDF (download intercept vs `page.pdf()`)