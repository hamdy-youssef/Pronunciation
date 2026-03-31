from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, validator
from app.services.search_service import search_service
from app.services.youtube_service import youtube_service
from app.services.transcript_service import transcript_service
from app.services.translation_service import translation_service
import logging
import re

logger = logging.getLogger(__name__)
router = APIRouter()


class SearchQuery(BaseModel):
    q: str
    accent: str = "us"
    
    @validator('q')
    def validate_query(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError('Query must be at least 2 characters')
        
        if not re.match(r'^[a-zA-Z\s]+$', v):
            raise ValueError('Only letters and spaces allowed')
        
        return v.strip()


class TranslateRequest(BaseModel):
    text: str
    target_lang: str = "en"


class SearchResult(BaseModel):
    videoId: str
    timestamp: float
    sentence: str


@router.get("/search")
async def search(q: str, accent: str = "us"):
    if not q or len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")
    
    if not re.match(r'^[a-zA-Z\s]+$', q):
        raise HTTPException(status_code=400, detail="Only letters and spaces allowed")
    
    query = q.strip().lower()
    
    try:
        videos = await youtube_service.search_videos(query, accent, max_results=10)
        
        if not videos:
            return {"error": "No videos found"}
        
        occurrences = []
        
        for video in videos[:5]:
            captions = await youtube_service.get_captions(video['id'])
            
            if not captions:
                continue
            
            processed = transcript_service.process_captions(captions)
            
            for cap in processed:
                cap['videoId'] = video['id']
                cap['video_title'] = video['title']
                cap['video_channel'] = video['channel']
                
                if query in cap['text']:
                    occurrences.append({
                        "videoId": video['id'],
                        "timestamp": cap['timestamp'],
                        "sentence": cap.get('original_text', cap['text']),
                        "video_title": video['title'],
                        "video_channel": video['channel']
                    })
        
        if not occurrences:
            return {"error": "No match found in any transcripts"}
        
        return {"results": occurrences}
    
    except Exception as e:
        logger.error(f"Search error: {e}")
        return {"error": str(e)}


@router.post("/translate")
async def translate(request: TranslateRequest):
    result = await translation_service.translate(request.text, request.target_lang)
    return result


@router.get("/health")
async def health():
    return {"status": "healthy"}
