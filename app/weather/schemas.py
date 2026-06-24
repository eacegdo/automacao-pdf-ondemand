from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class WeatherRequest(BaseModel):
    city: str = Field(..., examples=["São Vicente"], description="Cidade a pesquisar")
    lang: str = Field(default="pt-BR", description="Locale do browser")
    headless: bool = Field(default=True, description="False abre browser visível")


class WeatherCondition(BaseModel):
    temperature_c: Optional[float] = Field(None, description="Temperatura em °C")
    condition: Optional[str] = Field(None, description="Ex: 'Chuva leve'")
    humidity_pct: Optional[int] = None
    wind_kmh: Optional[float] = None
    precipitation_pct: Optional[int] = None
    datetime_local: Optional[str] = Field(None, description="Data/hora local do Google")


class WeatherResponse(BaseModel):
    city: str
    query_used: str
    scraped_at: datetime
    data: WeatherCondition
    source: str = "google-weather-widget"
