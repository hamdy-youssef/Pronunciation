import yt_dlp
import asyncio
import logging

logger = logging.getLogger(__name__)


class YoutubeService:
    def __init__(self):
        self.ydl_opts = {
            'quiet': True,
            'extract_flat': False,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['en'],
            'skip_download': True,
            'no_warnings': True,
        }

    async def get_video_info(self, video_id: str) -> dict:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._extract_video_info, video_id)

    def _extract_video_info(self, video_id: str) -> dict:
        url = f"https://www.youtube.com/watch?v={video_id}"
        opts = self.ydl_opts.copy()
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                return {
                    'id': info.get('id'),
                    'title': info.get('title'),
                    'channel': info.get('uploader'),
                    'duration': info.get('duration', 0),
                }
            except Exception as e:
                logger.error(f"Failed to get video info for {video_id}: {e}")
                return None

    async def get_captions(self, video_id: str) -> list:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._extract_captions, video_id)

    def _extract_captions(self, video_id: str) -> list:
        url = f"https://www.youtube.com/watch?v={video_id}"
        opts = self.ydl_opts.copy()
        opts['getsubtitles'] = True
        
        captions = []
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                
                subtitles = info.get('subtitles') or info.get('automatic_captions')
                
                if subtitles and 'en' in subtitles:
                    for fmt in subtitles['en']:
                        if fmt.get('ext') in ['json3', 'vtt', 'srv1', 'srv2', 'srv3']:
                            caption_data = self._fetch_caption_format(video_id, fmt.get('ext'))
                            if caption_data:
                                return self._parse_captions(caption_data, fmt.get('ext'))
                
            except Exception as e:
                logger.error(f"Failed to get captions for {video_id}: {e}")
        
        return captions

    def _fetch_caption_format(self, video_id: str, fmt: str) -> str:
        import httpx
        urls = [
            f"https://www.youtube.com/api/timedtext?lang=en&v={video_id}&fmt=json3",
            f"https://www.youtube.com/api/timedtext?lang=en&v={video_id}&fmt=srv3",
        ]
        
        for url in urls:
            try:
                resp = httpx.get(url, timeout=10)
                if resp.status_code == 200:
                    return resp.text
            except:
                continue
        return None

    def _parse_captions(self, data: str, fmt: str) -> list:
        import json
        import re
        
        captions = []
        
        if fmt == 'json3':
            try:
                data_json = json.loads(data)
                events = data_json.get('events', [])
                
                for event in events:
                    segs = event.get('segs', [])
                    if not segs:
                        continue
                    
                    text = ' '.join(seg.get('utf8', '') for seg in segs).strip()
                    if not text:
                        continue
                    
                    captions.append({
                        'start': (event.get('tStartMs', 0)) / 1000,
                        'duration': (event.get('dDurationMs', 3000)) / 1000,
                        'text': text
                    })
            except:
                pass
        
        elif 'srv' in fmt:
            import xml.etree.ElementTree as ET
            try:
                root = ET.fromstring(data)
                ns = {'yt': 'http://www.youtube.com/syndication/tt'}
                
                for p in root.findall('.//p', ns):
                    text = p.text or ''
                    if text.strip():
                        captions.append({
                            'start': int(p.get('t', 0)) / 1000,
                            'duration': int(p.get('d', 3000)) / 1000,
                            'text': text.strip()
                        })
            except:
                pass
        
        return captions

    async def search_videos(self, query: str, accent: str = "us", max_results: int = 20) -> list:
        loop = asyncio.get_event_loop()
        
        accent_query = {
            'us': 'american pronunciation interview',
            'uk': 'british pronunciation bbc interview',
            'au': 'australian pronunciation interview'
        }.get(accent, 'pronunciation interview')
        
        search_query = f"{query} {accent_query} podcast"
        
        return await loop.run_in_executor(None, self._search_youtube, search_query, max_results)

    def _search_youtube(self, query: str, max_results: int) -> list:
        opts = {
            'quiet': True,
            'no_warnings': True,
            'default_search': 'ytsearch20',
            'extract_flat': True,
        }
        
        videos = []
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(f"ytsearch20:{query}", download=False)
                
                if info and info.get('entries'):
                    for entry in info['entries']:
                        videos.append({
                            'id': entry.get('id'),
                            'title': entry.get('title'),
                            'channel': entry.get('channel') or entry.get('uploader', 'Unknown')
                        })
            except Exception as e:
                logger.error(f"Search failed: {e}")
        
        return videos[:max_results]


youtube_service = YoutubeService()
