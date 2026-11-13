from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.core.config import settings
from app.core.database import Base, engine, SessionLocal
from app.models import *  # register models with SQLAlchemy metadata
from app.services.seed import seed_demo_data
from app.services.assignments import process_expired_offers

async def deadline_worker():
    while True:
        await asyncio.sleep(5)
        try:
            with SessionLocal() as db:
                process_expired_offers(db)
        except Exception:
            # Keep the API alive; the authenticated admin job endpoint is a manual fallback.
            await asyncio.sleep(5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if settings.seed_demo_data:
        with SessionLocal() as db: seed_demo_data(db)
    worker = asyncio.create_task(deadline_worker())
    try:
        yield
    finally:
        worker.cancel()
        try: await worker
        except asyncio.CancelledError: pass

app = FastAPI(title=settings.app_name, version="0.1.0", description="ResQNet animal emergency coordination API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"], allow_headers=["Authorization", "Content-Type"])
app.include_router(router, prefix=settings.api_v1_prefix)

@app.get("/health")
def health():
    return {"status": "ok", "service": "resqnet-api", "environment": settings.environment}
