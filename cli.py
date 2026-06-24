#!/usr/bin/env python3
"""
CLI de clima: busca dados via Google (scraping) e imprime no terminal.
"""
import asyncio
import argparse

from app.weather.schemas import WeatherRequest
from app.weather.service import get_weather


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Busca clima via Google (scraping).")
    p.add_argument("city", help="Nome da cidade, ex: 'São Vicente'")
    p.add_argument("--lang", default="pt-BR", help="Locale do browser (padrão: pt-BR)")
    p.add_argument("--json", dest="as_json", action="store_true", help="Saída em JSON")
    p.add_argument("--show-browser", action="store_true", help="Abre browser visível (debug)")
    return p.parse_args()


async def main() -> None:
    args = parse_args()

    result = await get_weather(WeatherRequest(
        city=args.city,
        lang=args.lang,
        headless=not args.show_browser,
    ))

    if args.as_json:
        print(result.model_dump_json(indent=2))
        return

    d = result.data
    print(f"\nClima em {result.city}  ({d.datetime_local or ''})")
    print(f"  {d.condition or 'N/A'}  {d.temperature_c}°C")
    print(f"  Umidade: {d.humidity_pct}%   Vento: {d.wind_kmh} km/h")
    print(f"  Precipitação: {d.precipitation_pct}%")
    print(f"\n  Consultado em: {result.scraped_at.isoformat()}")


if __name__ == "__main__":
    asyncio.run(main())
