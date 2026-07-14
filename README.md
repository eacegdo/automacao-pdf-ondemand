# Robô EACE — Automação de PDF

Robô que faz login na intranet EACE, navega até o Status Report e retorna o PDF via API HTTP.

## Tecnologias

- Python + FastAPI
- Playwright (Chromium headless)
- Docker

## Instalação

```bash
git clone https://github.com/EAC_ORG/automacao-pdf-ondemand.git
cd automacao-pdf-ondemand
cp .env.example .env
# editar .env com EACE_EMAIL e EACE_PASSWORD
```

## Uso

### Com Docker

```bash
docker build -t eace-robo .
docker run --rm -p 8000:8000 --env-file .env eace-robo
```

### Sem Docker

```bash
pip install -r requirements.txt
playwright install chromium
python3 eace_cli.py
```

## Endpoints

| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/report/run-report` | Gera e retorna o Status Report em PDF |
| `GET`  | `/weather/?city=São Vicente` | Retorna dados de clima |

## Variáveis de Ambiente

| Variável | Descrição |
|----------|-----------|
| `EACE_EMAIL` | E-mail de acesso à intranet |
| `EACE_PASSWORD` | Senha de acesso à intranet |
| `API_KEY` | Chave de autenticação da API |

## Autenticação

Todos os endpoints exigem o header `X-API-Key`:

```bash
curl -X POST http://localhost:8000/report/run-report \
  -H "X-API-Key: sua-chave-aqui" \
  --output relatorio.pdf
```


### Rodar local rapido

pip install -r requirements.txt && playwright install chromium && python3 eace_cli.py

Depois de subir, testa em outro terminal:

curl -X POST http://localhost:8000/report/run-report \
  -H "X-API-Key: $(grep API_KEY .env | cut -d= -f2)" \
  --output relatorio.pdf

## Autor

**Wellington Santos**

