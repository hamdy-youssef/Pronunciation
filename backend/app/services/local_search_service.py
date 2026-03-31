import json
import os
import logging

logger = logging.getLogger(__name__)

DATA_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'transcripts.json')


class LocalSearchService:
    def __init__(self):
        self.transcripts = []
        self._load_data()

    def _load_data(self):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                self.transcripts = data.get('transcripts', [])
                logger.info(f"Loaded {len(self.transcripts)} video transcripts")
        except Exception as e:
            logger.error(f"Failed to load transcripts: {e}")
            self.transcripts = []

    def search(self, query: str, accent: str = "us", max_results: int = 20) -> list:
        if not query:
            return []
        
        query_lower = query.lower().strip()
        results = []
        
        for video in self.transcripts:
            captions = video.get('captions', [])
            
            for cap in captions:
                text_lower = cap.get('text', '').lower()
                
                if query_lower in text_lower:
                    results.append({
                        'videoId': video.get('videoId'),
                        'timestamp': cap.get('start', 0),
                        'sentence': cap.get('text'),
                        'video_title': video.get('title'),
                        'video_channel': video.get('channel')
                    })
        
        results.sort(key=lambda x: x['timestamp'])
        
        return results[:max_results]

    def get_all_words(self) -> list:
        words = set()
        for video in self.transcripts:
            for cap in video.get('captions', []):
                text = cap.get('text', '').lower()
                for word in text.split():
                    cleaned = ''.join(c for c in word if c.isalpha())
                    if len(cleaned) > 2:
                        words.add(cleaned)
        return sorted(list(words))[:100]


local_search_service = LocalSearchService()
