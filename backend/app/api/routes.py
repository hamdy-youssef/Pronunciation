from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, validator
from app.services.youtube_service import youtube_service
from app.services.transcript_service import transcript_service
from app.services.translation_service import translation_service
from app.services.local_search_service import local_search_service
import logging
import re

logger = logging.getLogger(__name__)
router = APIRouter()


class TranslateRequest(BaseModel):
    text: str
    target_lang: str = "en"


@router.get("/search")
async def search(q: str, accent: str = "us"):
    if not q or len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")
    
    if not re.match(r'^[a-zA-Z\s]+$', q):
        raise HTTPException(status_code=400, detail="Only letters and spaces allowed")
    
    query = q.strip().lower()
    
    try:
        results = local_search_service.search(query, accent, max_results=20)
        
        if not results:
            available = local_search_service.get_all_words()[:10]
            return {
                "error": f"No matches found for '{query}'. Try: " + ", ".join(available),
                "available_words": available
            }
        
        return {"results": results, "count": len(results)}
    
    except Exception as e:
        logger.error(f"Search error: {e}")
        return {"error": f"Search failed: {str(e)}. Please try again later."}


@router.post("/translate")
async def translate(request: TranslateRequest):
    result = await translation_service.translate(request.text, request.target_lang)
    return result


@router.get("/health")
async def health():
    return {"status": "healthy"}
