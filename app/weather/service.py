import re
from datetime import datetime, timezone
from typing import Optional

from app.core.browser import get_browser_context
from app.weather.scraper import scrape_weather
from app.weather.schemas import WeatherRequest, WeatherResponse, WeatherCondition


def _parse_float(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    cleaned = re.sub(r"[^\d.,]", "", value).replace(",", ".")
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def _parse_int(value: Optional[str]) -> Optional[int]:
    result = _parse_float(value)
    return int(result) if result is not None else None


async def get_weather(request: WeatherRequest) -> WeatherResponse:
    query = f"clima {request.city}"

    async with get_browser_context(locale=request.lang, headless=request.headless) as context:
        raw = await scrape_weather(context, query)

    condition = WeatherCondition(
        temperature_c=_parse_float(raw.get("temperature")),
        condition=raw.get("condition"),
        humidity_pct=_parse_int(raw.get("humidity")),
        wind_kmh=_parse_float(raw.get("wind")),
        precipitation_pct=_parse_int(raw.get("precipitation")),
        datetime_local=raw.get("datetime"),
    )

    return WeatherResponse(
        city=request.city,
        query_used=query,
        scraped_at=datetime.now(timezone.utc),
        data=condition,
    )
