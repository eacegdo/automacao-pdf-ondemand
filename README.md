# Robô EACE — Automação de PDF

Robô que faz login na intranet EACE, navega até o Status Report e retorna o PDF via API HTTP.

## Estrutura

```
app/
├── core/browser.py       # contexto Playwright compartilhado
├── eace/
│   ├── scraper.py        # lógica do robô
│   └── router.py         # POST /report/run-report
└── weather/
    ├── schemas.py
    ├── scraper.py
    ├── service.py
    └── router.py         # GET /weather/
eace_cli.py               # CLI local do robô
cli.py                    # CLI local de clima
```

---

## Rodando local (Docker)

### 1. Configurar credenciais

```bash
cp .env.example .env
# editar .env com EACE_EMAIL e EACE_PASSWORD
```

### 2. Build da imagem

```bash
docker build -t eace-robo .
```

> Primeira vez demora ~5 min — imagem Playwright tem ~1.5 GB.

### 3. Subir o container

```bash
docker run --rm -p 8000:8000 \
  --env-file .env \
  eace-robo
```

### 4. Testar

```bash
# Baixa o PDF gerado
curl -X POST http://localhost:8000/report/run-report --output relatorio.pdf

# Swagger UI (testar no browser)
open http://localhost:8000/docs
```

O endpoint `POST /report/run-report` roda o robô e retorna o PDF diretamente — nada é salvo em disco.

### CLI (sem Docker)

```bash
pip install -r requirements.txt
playwright install chromium

python3 eace_cli.py               # salva PDF em output/
python3 eace_cli.py --show-browser  # abre browser visível (debug)
```

---

## Deploy no EasyPanel

### Pré-requisitos

- Repositório no GitHub com o código
- EasyPanel com pelo menos **1 GB RAM** disponível para o serviço

### Passo a passo

**1. Criar o serviço**

- EasyPanel → **Create Service** → **App**
- Conectar repositório GitHub
- Build method: **Dockerfile**

**2. Configurar variáveis de ambiente**

No painel do serviço → **Environment**:

```
EACE_EMAIL=seu@email.com
EACE_PASSWORD=suasenha
```

**3. Configurar porta**

- Port: `8000`

**4. Deploy**

Clicar em **Deploy**. O EasyPanel vai fazer o build da imagem e subir o container.

### Testar no EasyPanel

```bash
curl -X POST https://<seu-dominio>/report/run-report --output relatorio.pdf
```

Ou acessar `https://<seu-dominio>/docs` para o Swagger UI.

---

## Endpoints

| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/report/run-report` | Gera e retorna o Status Report em PDF |
| `GET`  | `/weather/?city=São Vicente` | Retorna dados de clima via Google |

## Observações

- O robô usa Chromium headless — uma execução por vez (requisições simultâneas retornam `429`)
- Credenciais nunca devem ser commitadas — usar variáveis de ambiente sempre
- Se o site da EACE mudar o HTML, os seletores em `app/eace/scraper.py` precisam ser atualizados

---

## Desenvolvido por

**Wellington Santos**
