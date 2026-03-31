from elasticsearch import AsyncElasticsearch
from app.core.config import get_settings
import logging
import json
import redis.asyncio as redis

logger = logging.getLogger(__name__)


class SearchService:
    def __init__(self):
        self.es_client = None
        self.redis_client = None
        self.index_name = "transcripts"

    async def initialize(self):
        settings = get_settings()
        
        try:
            self.es_client = AsyncElasticsearch([settings.elasticsearch_host])
            await self.es_client.info()
            logger.info(f"Connected to ElasticSearch at {settings.elasticsearch_host}")
        except Exception as e:
            logger.warning(f"Could not connect to ElasticSearch: {e}")
            self.es_client = None
        
        try:
            self.redis_client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                decode_responses=True
            )
            await self.redis_client.ping()
            logger.info(f"Connected to Redis at {settings.redis_host}")
        except Exception as e:
            logger.warning(f"Could not connect to Redis: {e}")
            self.redis_client = None

    async def close(self):
        if self.es_client:
            await self.es_client.close()
        if self.redis_client:
            await self.redis_client.close()

    async def create_index(self):
        if not self.es_client:
            return
        
        exists = await self.es_client.indices.exists(index=self.index_name)
        if not exists:
            await self.es_client.indices.create(
                index=self.index_name,
                body={
                    "mappings": {
                        "properties": {
                            "text": {"type": "text", "analyzer": "standard"},
                            "videoId": {"type": "keyword"},
                            "title": {"type": "text"},
                            "channel": {"type": "text"},
                            "timestamp": {"type": "float"},
                            "duration": {"type": "float"},
                            "original_text": {"type": "text"}
                        }
                    }
                }
            )
            logger.info(f"Created index {self.index_name}")

    async def index_transcript(self, video_id: str, transcript_data: dict):
        if not self.es_client:
            return
        
        await self.create_index()
        
        doc = {
            "videoId": video_id,
            "text": transcript_data.get('text', ''),
            "timestamp": transcript_data.get('timestamp', 0),
            "duration": transcript_data.get('duration', 0),
            "title": transcript_data.get('title', ''),
            "channel": transcript_data.get('channel', ''),
            "original_text": transcript_data.get('original_text', '')
        }
        
        await self.es_client.index(index=self.index_name, document=doc)

    async def seed_corpus(self, corpus: list):
        if not self.es_client or not corpus:
            return

        await self.create_index()
        for entry in corpus:
            await self.es_client.index(
                index=self.index_name,
                document={
                    "videoId": entry.get('videoId', ''),
                    "text": entry.get('clean_text', entry.get('text', '')),
                    "timestamp": entry.get('timestamp', 0),
                    "duration": entry.get('duration', 0),
                    "title": entry.get('videoTitle', ''),
                    "channel": entry.get('channel', ''),
                    "original_text": entry.get('text', ''),
                },
            )

    async def search(self, query: str, limit: int = 10) -> list:
        settings = get_settings()
        cache_key = f"search:{query}"
        
        if self.redis_client:
            try:
                cached = await self.redis_client.get(cache_key)
                if cached:
                    logger.info(f"Cache hit for query: {query}")
                    return json.loads(cached)
            except Exception as e:
                logger.warning(f"Redis cache error: {e}")
        
        results = []
        
        if self.es_client:
            try:
                response = await self.es_client.search(
                    index=self.index_name,
                    body={
                        "query": {
                            "bool": {
                                "should": [
                                    {"match_phrase": {"text": {"query": query, "boost": 5}}},
                                    {"match": {"text": {"query": query, "fuzziness": "AUTO", "boost": 3}}},
                                    {"match": {"original_text": {"query": query, "fuzziness": "AUTO"}}},
                                ]
                            }
                        },
                        "size": limit,
                        "sort": [{"_score": "desc"}]
                    }
                )
                
                results = [
                    {
                        "videoId": hit["_source"]["videoId"],
                        "timestamp": hit["_source"]["timestamp"],
                        "sentence": hit["_source"].get("original_text", hit["_source"]["text"]),
                        "score": hit["_score"]
                    }
                    for hit in response["hits"]["hits"]
                ]
            except Exception as e:
                logger.error(f"ElasticSearch query error: {e}")
        
        if self.redis_client and results:
            try:
                await self.redis_client.setex(
                    cache_key,
                    settings.search_cache_ttl,
                    json.dumps(results)
                )
            except Exception as e:
                logger.warning(f"Redis cache set error: {e}")
        
        return results


search_service = SearchService()
