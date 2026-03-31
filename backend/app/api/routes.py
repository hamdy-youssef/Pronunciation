import logging
import re

from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.services.search_service import search_service
from app.services.translation_service import translation_service

logger = logging.getLogger(__name__)
router = APIRouter()


class TranslateRequest(BaseModel):
    text: str
    target_lang: Optional[str] = None


@router.get('/search')
async def search(q: str, accent: str = 'us', limit: int = 10):
    query = (q or '').strip()

    if len(query) < 2:
        return JSONResponse(status_code=400, content={'error': 'Query must be at least 2 characters'})

    if not re.match(r"^[a-zA-Z\s'’-]+$", query):
        return JSONResponse(status_code=400, content={'error': 'Only letters, spaces, apostrophes, and hyphens are allowed'})

    try:
        result = await search_service.search_best(query, accent=accent, limit=limit)

        if not result:
            return JSONResponse(status_code=404, content={'error': 'No match found'})

        results = await search_service.search(query, accent=accent, limit=limit)

        return {
            'query': query,
            'accent': accent,
            'results': results,
            'videoId': result['videoId'],
            'timestamp': result['timestamp'],
            'duration': result.get('duration', 3.5),
            'sentence': result['sentence'],
            'subtitleText': result.get('subtitleText', result['sentence']),
            'videoTitle': result.get('videoTitle', ''),
            'channel': result.get('channel', ''),
            'score': result.get('score', 0),
            'context': result.get('context', []),
            'subtitleCues': result.get('subtitleCues', []),
            'subtitleTranscript': result.get('subtitleTranscript', ''),
            'source': result.get('source', ''),
            'totalResults': len(results),
        }
    except Exception as e:
        logger.error('Search error: %s', e)
        return JSONResponse(status_code=500, content={'error': 'Search failed'})


@router.get('/transcripts/{video_id}')
async def transcript(video_id: str):
    data = await search_service.get_transcript(video_id)
    if not data:
        return JSONResponse(status_code=404, content={'error': 'Transcript not found'})

    return data


@router.get('/videos/{video_id}')
async def video(video_id: str):
    data = await search_service.get_transcript(video_id)
    if not data:
        return JSONResponse(status_code=404, content={'error': 'Video not found'})

    return data


@router.get('/videos/{video_id}/captions')
async def video_captions(video_id: str):
    data = await search_service.get_transcript(video_id)
    if not data:
        return JSONResponse(status_code=404, content={'error': 'Captions not found'})

    return {'videoId': video_id, 'captions': data.get('captions', [])}


@router.get('/library/stats')
async def library_stats():
    return search_service.get_stats()


@router.post('/translate')
async def translate(request: TranslateRequest):
    try:
        return await translation_service.translate(request.text, request.target_lang)
    except Exception as e:
        logger.error('Translate error: %s', e)
        return JSONResponse(status_code=500, content={'error': 'Translation failed'})


@router.get('/health')
async def health():
    return {'status': 'healthy'}
