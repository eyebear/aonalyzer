from fastapi import FastAPI

from app.api.error_handlers import register_error_handlers
from app.api.routes.action_routes import router as action_router
from app.api.routes.agent_routes import router as agent_router
from app.api.routes.ai_analysis_routes import router as ai_analysis_router
from app.api.routes.ai_provider_routes import router as ai_provider_router
from app.api.routes.brief_routes import router as brief_router
from app.api.routes.chat_routes import router as chat_router
from app.api.routes.data_quality_routes import router as data_quality_router
from app.api.routes.decision_routes import router as decision_router
from app.api.routes.do_not_touch_routes import router as do_not_touch_router
from app.api.routes.earnings_routes import router as earnings_router
from app.api.routes.event_routes import router as event_router
from app.api.routes.export_import_routes import router as export_import_router
from app.api.routes.governance_routes import router as governance_router
from app.api.routes.hard_filter_routes import router as hard_filter_router
from app.api.routes.health_routes import router as health_router
from app.api.routes.iv_routes import router as iv_router
from app.api.routes.learning_routes import router as learning_router
from app.api.routes.lifecycle_routes import router as lifecycle_router
from app.api.routes.manual_option_routes import router as manual_option_router
from app.api.routes.market_data_routes import router as market_data_router
from app.api.routes.market_regime_routes import router as market_regime_router
from app.api.routes.memory_routes import router as memory_router
from app.api.routes.model_routes import router as model_router
from app.api.routes.option_chain_routes import router as option_chain_router
from app.api.routes.option_suitability_routes import router as option_suitability_router
from app.api.routes.outcome_routes import router as outcome_router
from app.api.routes.pipeline_routes import router as pipeline_router
from app.api.routes.profile_routes import router as profile_router
from app.api.routes.rejection_routes import router as rejection_router
from app.api.routes.review_routes import router as review_router
from app.api.routes.settings_routes import router as platform_settings_router
from app.api.routes.setup_detection_routes import router as setup_detection_router
from app.api.routes.stock_setup_routes import router as stock_setup_router
from app.api.routes.system_routes import router as system_router
from app.api.routes.technical_routes import router as technical_router
from app.api.routes.ticker_routes import router as ticker_router
from app.api.routes.user_action_routes import router as user_action_router
from app.api.routes.worklist_routes import router as worklist_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Local equity and options research platform.",
    version="0.52.0",
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
app.include_router(hard_filter_router)
app.include_router(decision_router)
app.include_router(action_router)
app.include_router(rejection_router)
app.include_router(do_not_touch_router)
app.include_router(lifecycle_router)
app.include_router(review_router)
app.include_router(worklist_router)
app.include_router(brief_router)
app.include_router(chat_router)
app.include_router(user_action_router)
app.include_router(outcome_router)
app.include_router(memory_router)
app.include_router(learning_router)
app.include_router(governance_router)
app.include_router(platform_settings_router)
app.include_router(export_import_router)
app.include_router(pipeline_router)