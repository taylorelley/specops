"""FastAPI application for admin dashboard."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from specops import __version__
from specops.apis.agents import router as agents_router
from specops.apis.api_tools import router as api_tools_router
from specops.apis.auth import router as auth_router
from specops.apis.config import router as config_router
from specops.apis.control import router as control_router
from specops.apis.executions import router as executions_router
from specops.apis.llm_providers import router as llm_providers_router
from specops.apis.logs import router as logs_router
from specops.apis.mcp_registry import router as mcp_registry_router
from specops.apis.plan_templates import router as plan_templates_router
from specops.apis.plan_workspace import router as plan_workspace_router
from specops.apis.plans import router as plans_router
from specops.apis.providers import router as providers_router
from specops.apis.shares import router as shares_router
from specops.apis.skills import router as skills_router
from specops.apis.software import router as software_router
from specops.apis.terminal import router as terminal_router
from specops.apis.users import router as users_router
from specops.apis.webhooks import router as webhooks_router
from specops.apis.workspace import router as workspace_router
from specops.core.acp import RunStore
from specops.core.database import get_database
from specops.core.runtimes.factory import get_runtime_backend
from specops.core.storage import get_storage_backend
from specops.core.store.activity_events import ActivityEventsStore
from specops.core.store.agents import AgentStore
from specops.core.store.execution_events import ExecutionEventsStore
from specops.core.store.executions import ExecutionsStore
from specops.core.store.process_logs import ProcessLogStore
from specops.core.ws import ConnectionManager
from specops.middleware.rate_limit import limiter
from specops_lib.activity import ActivityLogRegistry

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.storage = get_storage_backend()
    app.state.activity_registry = ActivityLogRegistry()
    app.state.activity_events_store = ActivityEventsStore(get_database())
    app.state.executions_store = ExecutionsStore(get_database())
    app.state.execution_events_store = ExecutionEventsStore(get_database())
    app.state.process_log_store = ProcessLogStore(
        app.state.storage,
        AgentStore(get_database(), app.state.storage),
    )
    app.state.ws_manager = ConnectionManager()
    app.state.run_store = RunStore()
    app.state.runtime = get_runtime_backend(
        storage=app.state.storage,
        ws_manager=app.state.ws_manager,
        activity_registry=app.state.activity_registry,
    )
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="SpecOps", version=__version__, lifespan=lifespan)
    cors_origins = [
        o.strip()
        for o in os.environ.get(
            "CORS_ORIGINS", "http://localhost:5173,http://localhost:8080"
        ).split(",")
        if o.strip()
    ]
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(agents_router)
    app.include_router(shares_router)
    app.include_router(plans_router)
    app.include_router(plan_templates_router)
    app.include_router(plan_workspace_router)
    app.include_router(skills_router)
    app.include_router(mcp_registry_router)
    app.include_router(software_router)
    app.include_router(workspace_router)
    app.include_router(config_router)
    app.include_router(control_router)
    app.include_router(executions_router)
    app.include_router(api_tools_router)
    app.include_router(llm_providers_router)
    app.include_router(logs_router)
    app.include_router(terminal_router)
    app.include_router(webhooks_router)
    app.include_router(providers_router)

    # Serve SPA static assets and fallback (single-container / standalone Docker)
    _static_dir = Path(__file__).parent / "static"
    _assets_dir = _static_dir / "assets"
    _index_path = _static_dir / "index.html"
    if _assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")
    if _index_path.exists():

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            return FileResponse(str(_index_path))

    return app


app = create_app()
