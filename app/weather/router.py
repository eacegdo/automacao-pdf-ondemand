from fastapi import APIRouter, Query, HTTPException

from app.weather.schemas import WeatherRequest, WeatherResponse
from app.weather.service import get_weather

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("/", response_model=WeatherResponse, summary="Busca clima via Google")
async def weather_endpoint(
    city: str = Query(..., examples=["São Vicente"], description="Cidade a pesquisar"),
    lang: str = Query(default="pt-BR", description="Locale do browser"),
) -> WeatherResponse:
    try:
        return await get_weather(WeatherRequest(city=city, lang=lang))
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Erro no scraper: {exc}")
