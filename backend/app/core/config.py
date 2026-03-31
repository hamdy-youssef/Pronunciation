from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    elasticsearch_host: str = "http://localhost:9200"
    redis_host: str = "localhost"
    redis_port: int = 6379
    youtube_caching_ttl: int = 3600
    search_cache_ttl: int = 300
    
    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    return Settings()
