import os

from fastapi import APIRouter, Header, HTTPException, Query

from app.weather.schemas import WeatherRequest, WeatherResponse
from app.weather.service import get_weather

router = APIRouter(prefix="/weather", tags=["weather"])


def _check_api_key(x_api_key: str | None):
    api_key = os.environ.get("API_KEY")
    if api_key and x_api_key != api_key:
        raise HTTPException(status_code=401, detail="API key inválida ou ausente")


@router.get("/", response_model=WeatherResponse, summary="Busca clima via Google")
async def weather_endpoint(
    city: str = Query(..., examples=["São Vicente"], description="Cidade a pesquisar"),
    lang: str = Query(default="pt-BR", description="Locale do browser"),
    x_api_key: str | None = Header(default=None),
) -> WeatherResponse:
    _check_api_key(x_api_key)
    try:
        return await get_weather(WeatherRequest(city=city, lang=lang))
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Erro no scraper: {exc}")
