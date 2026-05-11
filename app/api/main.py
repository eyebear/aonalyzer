from fastapi import FastAPI

from app.api.error_handlers import register_error_handlers
from app.api.routes.agent_routes import router as agent_router
from app.api.routes.data_quality_routes import router as data_quality_router
from app.api.routes.health_routes import router as health_router
from app.api.routes.manual_option_routes import router as manual_option_router
from app.api.routes.market_data_routes import router as market_data_router
from app.api.routes.option_chain_routes import router as option_chain_router
from app.api.routes.profile_routes import router as profile_router
from app.api.routes.system_routes import router as system_router
from app.api.routes.ticker_routes import router as ticker_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Local equity and options research platform.",
    version="0.8.0",
)

register_error_handlers(app)

app.include_router(health_router)
app.include_router(system_router)
app.include_router(ticker_router)
app.include_router(profile_router)
app.include_router(agent_router)
app.include_router(data_quality_router)
app.include_router(market_data_router)
app.include_router(option_chain_router)
app.include_router(manual_option_router)