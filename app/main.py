from fastapi import FastAPI

from app.eace.router import router as eace_router
from app.weather.router import router as weather_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="EACE Automação",
        description="Robô EACE + scraping de clima.",
        version="1.0.0",
    )
    app.include_router(eace_router)
    app.include_router(weather_router)
    return app


app = create_app()
