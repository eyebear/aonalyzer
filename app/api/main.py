from fastapi import FastAPI

from app.api.error_handlers import register_error_handlers
from app.api.routes.agent_routes import router as agent_router
from app.api.routes.ai_analysis_routes import router as ai_analysis_router
from app.api.routes.ai_provider_routes import router as ai_provider_router
from app.api.routes.data_quality_routes import router as data_quality_router
from app.api.routes.earnings_routes import router as earnings_router
from app.api.routes.event_routes import router as event_router
from app.api.routes.health_routes import router as health_router
from app.api.routes.iv_routes import router as iv_router
from app.api.routes.manual_option_routes import router as manual_option_router
from app.api.routes.market_data_routes import router as market_data_router
from app.api.routes.market_regime_routes import router as market_regime_router
from app.api.routes.model_routes import router as model_router
from app.api.routes.option_chain_routes import router as option_chain_router
from app.api.routes.option_suitability_routes import router as option_suitability_router
from app.api.routes.profile_routes import router as profile_router
from app.api.routes.setup_detection_routes import router as setup_detection_router
from app.api.routes.stock_setup_routes import router as stock_setup_router
from app.api.routes.system_routes import router as system_router
from app.api.routes.technical_routes import router as technical_router
from app.api.routes.ticker_routes import router as ticker_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Local equity and options research platform.",
    version="0.13.0",
)

register_error_handlers(app)

app.include_router(health_router)
app.include_router(system_router)
app.include_router(ticker_router)
app.include_router(profile_router)
app.include_router(agent_router)
app.include_router(ai_analysis_router)
app.include_router(ai_provider_router)
app.include_router(data_quality_router)
app.include_router(market_data_router)
app.include_router(market_regime_router)
app.include_router(model_router)
app.include_router(option_chain_router)
app.include_router(option_suitability_router)
app.include_router(manual_option_router)
app.include_router(event_router)
app.include_router(technical_router)
app.include_router(earnings_router)
app.include_router(iv_router)
app.include_router(stock_setup_router)
app.include_router(setup_detection_router)