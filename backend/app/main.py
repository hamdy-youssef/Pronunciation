from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import routes
from app.core.config import get_settings
from app.services.local_search_service import local_search_service
from app.services.search_service import search_service
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Pronunciation Platform API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes.router)


@app.on_event("startup")
async def startup():
    settings = get_settings()
    logger.info(f"Starting Pronunciation Platform API")
    logger.info(f"ElasticSearch: {settings.elasticsearch_host}")
    logger.info(f"Redis: {settings.redis_host}:{settings.redis_port}")
    await search_service.initialize()
    await search_service.seed_corpus(local_search_service.entries)


@app.on_event("shutdown")
async def shutdown():
    await search_service.close()


@app.get("/health")
async def health():
    return {"status": "healthy"}
