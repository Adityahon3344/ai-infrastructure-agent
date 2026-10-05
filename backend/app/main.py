from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db
from app.core.loop_registry import set_main_loop
from app.core.logging_config import configure_logging

from app.auth.routes import router as auth_router
from app.servers.routes import router as servers_router
from app.connections.routes import router as connections_router
from app.chat.routes import router as chat_router
from app.jobs.routes import router as jobs_router
from app.approval.routes import router as approval_router
from app.memory.routes import router as memory_router
from app.audit.routes import router as audit_router
from app.streaming.routes import router as streaming_router
from app.files.routes import router as files_router
from app.terminal.routes import router as terminal_router
from app.monitoring.routes import router as monitoring_router
from app.cost.routes import router as cost_router
from app.rollback.routes import router as rollback_router
from app.automations.routes import router as automations_router
from app.aws.routes import router as aws_router
from app.catalog.routes import router as catalog_router

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    set_main_loop(asyncio.get_event_loop())
    from app.automations.scheduler import start_scheduler
    start_scheduler()
    yield


app = FastAPI(
    title="AI Infrastructure Agent",
    description="Natural-language AI Infrastructure / DevOps Control Plane",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    auth_router, servers_router, connections_router, chat_router, jobs_router,
    approval_router, memory_router, audit_router, streaming_router, files_router,
    terminal_router, monitoring_router, cost_router, rollback_router,
    automations_router, aws_router, catalog_router,
):
    app.include_router(router)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "ai-infrastructure-agent"}
