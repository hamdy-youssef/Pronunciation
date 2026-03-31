import asyncio
import json
import logging
from difflib import SequenceMatcher
from typing import Optional

import redis.asyncio as redis
from elasticsearch import AsyncElasticsearch

from app.core.config import get_settings
from app.services.local_search_service import local_search_service
from app.services.youtube_service import youtube_service

logger = logging.getLogger(__name__)


class SearchService:
    def __init__(self):
        self.es_client = None
        self.redis_client = None
        self.index_name = "transcripts"

    @staticmethod
    def _normalize(text: str) -> str:
        text = (text or "").lower()
        import re

        text = re.sub(r"[^\w\s]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _build_result(self, entry: dict, source: str) -> dict:
        return {
            "videoId": entry.get("videoId", ""),
            "timestamp": float(entry.get("timestamp", 0) or 0),
            "duration": float(entry.get("duration", 3.5) or 3.5),
            "sentence": entry.get("sentence") or entry.get("text") or entry.get("subtitleText", ""),
            "subtitleText": entry.get("subtitleText") or entry.get("sentence") or entry.get("text", ""),
            "videoTitle": entry.get("videoTitle") or entry.get("title") or entry.get("video_title", ""),
            "channel": entry.get("channel") or entry.get("video_channel", ""),
            "score": float(entry.get("score", 0) or 0),
            "context": entry.get("context", []),
            "subtitleCues": entry.get("subtitleCues", []),
            "subtitleTranscript": entry.get("subtitleTranscript", ""),
            "source": source,
        }

    def _merge_results(self, results: list, extra_results: list) -> list:
        seen = set()
        merged = []

        for item in results + extra_results:
            key = (item.get("videoId", ""), round(float(item.get("timestamp", 0) or 0), 2))
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)

        merged.sort(key=lambda item: (-float(item.get("score", 0) or 0), float(item.get("timestamp", 0) or 0)))
        return merged

    def _score_entry(self, query: str, entry: dict) -> float:
        normalized_query = self._normalize(query)
        normalized_text = self._normalize(entry.get("text") or entry.get("sentence") or entry.get("subtitleText") or "")

        if not normalized_query or not normalized_text:
            return 0.0
        if normalized_query == normalized_text:
            return 100.0

        score = 0.0
        if normalized_query in normalized_text:
            score += 45.0
        if normalized_text in normalized_query:
            score += 18.0

        query_words = set(normalized_query.split())
        text_words = set(normalized_text.split())
        if query_words:
            score += (len(query_words & text_words) / len(query_words)) * 25.0

        score += SequenceMatcher(None, normalized_query, normalized_text).ratio() * 20.0

        if normalized_text.startswith(normalized_query):
            score += 5.0

        return round(score, 3)

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
        await youtube_service.close()

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
                            "subtitleText": {"type": "text", "analyzer": "standard"},
                            "videoId": {"type": "keyword"},
                            "title": {"type": "text"},
                            "channel": {"type": "text"},
                            "timestamp": {"type": "float"},
                            "duration": {"type": "float"},
                            "original_text": {"type": "text"},
                            "captionCount": {"type": "integer"}
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
            "subtitleText": transcript_data.get('subtitleText', transcript_data.get('text', '')),
            "timestamp": transcript_data.get('timestamp', 0),
            "duration": transcript_data.get('duration', 0),
            "title": transcript_data.get('title', ''),
            "channel": transcript_data.get('channel', ''),
            "original_text": transcript_data.get('original_text', ''),
            "captionCount": transcript_data.get('captionCount', 1),
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
                    "subtitleText": entry.get('text', ''),
                    "timestamp": entry.get('timestamp', 0),
                    "duration": entry.get('duration', 0),
                    "title": entry.get('videoTitle', ''),
                    "channel": entry.get('channel', ''),
                    "original_text": entry.get('text', ''),
                    "captionCount": 1,
                },
            )

    async def _search_elasticsearch(self, query: str, limit: int = 10) -> list:
        if not self.es_client:
            return []

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
                    "sort": [{"_score": "desc"}],
                },
            )

            return [
                {
                    "videoId": hit["_source"]["videoId"],
                    "timestamp": hit["_source"].get("timestamp", 0),
                    "duration": hit["_source"].get("duration", 3.5),
                    "sentence": hit["_source"].get("original_text", hit["_source"].get("text", "")),
                    "subtitleText": hit["_source"].get("subtitleText", hit["_source"].get("text", "")),
                    "videoTitle": hit["_source"].get("title", ""),
                    "channel": hit["_source"].get("channel", ""),
                    "score": hit.get("_score", 0),
                    "source": "elasticsearch",
                }
                for hit in response["hits"]["hits"]
            ]
        except Exception as e:
            logger.error(f"ElasticSearch query error: {e}")
            return []

    async def _search_live(self, query: str, accent: str, limit: int = 10) -> list:
        videos = await youtube_service.search_videos(query, accent=accent, max_results=max(limit * 2, 10))
        if not videos:
            return []

        async def fetch_video(video: dict):
            try:
                captions = await youtube_service.get_captions(video.get("id", ""))
                return video, captions
            except Exception:
                return None

        fetched = await asyncio.gather(*(fetch_video(video) for video in videos[: max(4, limit)]))
        candidates = []

        for item in fetched:
            if not item:
                continue
            video, captions = item
            if not captions:
                continue

            for index, caption in enumerate(captions):
                text = (caption.get("text") or "").strip()
                if not text:
                    continue

                next_start = captions[index + 1].get("start", caption.get("start", 0) + 3.5) if index + 1 < len(captions) else caption.get("start", 0) + 3.5
                entry = {
                    "videoId": video.get("id", ""),
                    "videoTitle": video.get("title", ""),
                    "channel": video.get("channel", ""),
                    "text": text,
                    "subtitleText": text,
                    "timestamp": float(caption.get("start", 0) or 0),
                    "duration": max(1.0, round(float(next_start or 0) - float(caption.get("start", 0) or 0), 2)),
                }
                score = self._score_entry(query, entry)
                if score <= 0:
                    continue

                entry["score"] = score
                entry["source"] = "youtube"
                candidates.append(entry)

        candidates.sort(key=lambda item: (-item["score"], item["timestamp"]))
        return candidates[:limit]

    async def search(self, query: str, accent: str = "us", limit: int = 10) -> list:
        settings = get_settings()
        cache_key = f"search:{accent}:{query}:{limit}"
        
        if self.redis_client:
            try:
                cached = await self.redis_client.get(cache_key)
                if cached:
                    logger.info(f"Cache hit for query: {query}")
                    return json.loads(cached)
            except Exception as e:
                logger.warning(f"Redis cache error: {e}")
        
        results = await self._search_elasticsearch(query, limit)

        local_results = local_search_service.search(query, accent=accent, max_results=limit)
        results = self._merge_results(results, [self._build_result(result, "local") for result in local_results])

        if len(results) < limit:
            live_results = await self._search_live(query, accent=accent, limit=limit)
            results = self._merge_results(results, [self._build_result(result, result.get("source", "youtube")) for result in live_results])

        results = results[:limit]
        
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

    async def search_best(self, query: str, accent: str = "us", limit: int = 10) -> Optional[dict]:
        results = await self.search(query, accent=accent, limit=limit)
        if not results:
            return None

        best = results[0]
        best["context"] = await self.get_context(best["videoId"], best["timestamp"])
        best["subtitleCues"] = best["context"]
        best["subtitleTranscript"] = await self.get_transcript_text(best["videoId"])
        return best

    async def get_context(self, video_id: str, timestamp: float, window: int = 2) -> list:
        local_context = local_search_service.get_context(video_id, timestamp, window=window)
        if local_context:
            return local_context

        transcript = await self.get_transcript(video_id)
        if not transcript:
            return []

        captions = transcript.get("captions", [])
        if not captions:
            return []

        closest_index = 0
        closest_delta = abs(float(captions[0].get("timestamp", 0) or 0) - float(timestamp or 0))
        for index, caption in enumerate(captions):
            delta = abs(float(caption.get("timestamp", 0) or 0) - float(timestamp or 0))
            if delta < closest_delta:
                closest_delta = delta
                closest_index = index

        start = max(0, closest_index - max(0, int(window)))
        end = min(len(captions), closest_index + max(0, int(window)) + 1)

        context = []
        for item in captions[start:end]:
            context.append({
                "videoId": video_id,
                "timestamp": item.get("timestamp", 0),
                "duration": item.get("duration", 3.5),
                "sentence": item.get("sentence", item.get("subtitleText", "")),
                "subtitleText": item.get("subtitleText", item.get("sentence", "")),
                "video_title": transcript.get("title", ""),
                "video_channel": transcript.get("channel", ""),
                "isMatch": abs(float(item.get("timestamp", 0) or 0) - float(timestamp or 0)) < 0.001,
            })

        return context

    async def get_transcript(self, video_id: str) -> Optional[dict]:
        transcript = local_search_service.get_transcript(video_id)
        if transcript:
            return transcript

        try:
            captions = await youtube_service.get_captions(video_id)
        except Exception as e:
            logger.debug(f"Live transcript lookup failed for {video_id}: {e}")
            return None

        if not captions:
            return None

        cleaned = []
        for index, caption in enumerate(captions):
            text = (caption.get("text") or "").strip()
            if not text:
                continue

            next_start = captions[index + 1].get("start", caption.get("start", 0) + 3.5) if index + 1 < len(captions) else caption.get("start", 0) + 3.5
            cleaned.append({
                "videoId": video_id,
                "timestamp": float(caption.get("start", 0) or 0),
                "duration": max(1.0, round(float(next_start or 0) - float(caption.get("start", 0) or 0), 2)),
                "sentence": text,
                "subtitleText": text,
                "video_title": "",
                "video_channel": "",
            })

        return {
            "videoId": video_id,
            "title": "",
            "channel": "",
            "captionCount": len(cleaned),
            "subtitleTranscript": " ".join(item["sentence"] for item in cleaned),
            "captions": cleaned,
        }

    async def get_transcript_text(self, video_id: str) -> str:
        transcript = await self.get_transcript(video_id)
        if not transcript:
            return ""
        return transcript.get("subtitleTranscript", "")

    def get_stats(self) -> dict:
        return local_search_service.get_stats()


search_service = SearchService()
