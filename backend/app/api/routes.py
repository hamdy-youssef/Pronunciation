import logging
import re

from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.services.local_search_service import local_search_service
from app.services.translation_service import translation_service

logger = logging.getLogger(__name__)
router = APIRouter()


class TranslateRequest(BaseModel):
    text: str
    target_lang: Optional[str] = None


@router.get('/search')
async def search(q: str):
    query = (q or '').strip()

    if len(query) < 2:
        return JSONResponse(status_code=400, content={'error': 'Query must be at least 2 characters'})

    if not re.match(r'^[a-zA-Z\s]+$', query):
        return JSONResponse(status_code=400, content={'error': 'Only letters and spaces are allowed'})

    try:
        result = local_search_service.search_best(query)

        if not result:
            return JSONResponse(status_code=404, content={'error': 'No match found'})

        return {
            'videoId': result['videoId'],
            'timestamp': result['timestamp'],
            'duration': result.get('duration', 3.5),
            'sentence': result['sentence'],
            'videoTitle': result.get('video_title', ''),
            'channel': result.get('video_channel', ''),
            'score': result.get('score', 0),
        }
    except Exception as e:
        logger.error('Search error: %s', e)
        return JSONResponse(status_code=500, content={'error': 'Search failed'})


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
