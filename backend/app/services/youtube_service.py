import httpx
import asyncio
import logging
import json
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

INVIDIOUS_INSTANCES = [
    'https://invidious.fdn.fr',
    'https://invidious.snopyta.org',
    'https://yewtu.be',
    'https://redirect.invidious.io',
]


class YoutubeService:
    def __init__(self):
        pass

    async def get_captions(self, video_id: str) -> list:
        for instance in INVIDIOUS_INSTANCES:
            try:
                url = f"{instance}/api/v1/captions/{video_id}"
                async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        for cap in data:
                            if cap.get('languageCode') == 'en':
                                caption_url = cap.get('url')
                                if caption_url:
                                    return await self._fetch_caption_from_url(caption_url)
            except Exception as e:
                logger.debug(f"Invidious captions failed for {video_id}: {e}")
                continue
        
        return await self._get_captions_from_youtube_direct(video_id)

    async def _fetch_caption_from_url(self, url: str) -> list:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    text = resp.text
                    if not text:
                        return []
                    
                    if 'json3' in url or url.endswith('.json'):
                        return self._parse_json3(text)
                    elif 'srv3' in url or url.endswith('.srv3'):
                        return self._parse_srv3(text)
                    elif 'vtt' in url or url.endswith('.vtt'):
                        return self._parse_vtt(text)
        except Exception as e:
            logger.debug(f"Failed to fetch caption: {e}")
        
        return []

    async def _get_captions_from_youtube_direct(self, video_id: str) -> list:
        try:
            import yt_dlp
        except ImportError:
            return []
        
        loop = asyncio.get_event_loop()
        
        def fetch():
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
                'nocheckcertificate': True,
            }
            
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(
                        f'https://www.youtube.com/watch?v={video_id}',
                        download=False,
                        process=False
                    )
                    
                    subs = info.get('subtitles') or info.get('automatic_captions')
                    
                    if subs and 'en' in subs:
                        for fmt in subs['en']:
                            caption_url = fmt.get('url')
                            if caption_url:
                                try:
                                    resp = httpx.get(caption_url, timeout=10.0)
                                    if resp.status_code == 200:
                                        text = resp.text
                                        if 'json3' in caption_url:
                                            return self._parse_json3(text)
                                        elif 'srv3' in caption_url:
                                            return self._parse_srv3(text)
                                        elif 'vtt' in caption_url:
                                            return self._parse_vtt(text)
                                except:
                                    continue
                                    
            except Exception as e:
                logger.debug(f"yt-dlp failed for {video_id}: {e}")
            
            return []
        
        return await loop.run_in_executor(None, fetch)

    def _parse_json3(self, text: str) -> list:
        captions = []
        try:
            data = json.loads(text)
            events = data.get('events', [])
            
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
        except Exception as e:
            logger.debug(f"JSON3 parse error: {e}")
        
        return captions

    def _parse_srv3(self, text: str) -> list:
        captions = []
        try:
            root = ET.fromstring(text)
            
            for p in root.findall('.//p'):
                content = p.text
                if content and content.strip():
                    captions.append({
                        'start': int(p.get('t', 0)) / 1000,
                        'duration': int(p.get('d', 3000)) / 1000,
                        'text': content.strip()
                    })
        except Exception as e:
            logger.debug(f"SRV3 parse error: {e}")
        
        return captions

    def _parse_vtt(self, text: str) -> list:
        captions = []
        try:
            lines = text.split('\n')
            i = 0
            
            while i < len(lines):
                line = lines[i].strip()
                if '-->' in line:
                    start, _ = self._parse_vtt_timestamp(line)
                    text_lines = []
                    i += 1
                    while i < len(lines) and lines[i].strip() and '-->' not in lines[i]:
                        text_lines.append(lines[i].strip())
                        i += 1
                    if text_lines:
                        captions.append({
                            'start': start,
                            'duration': 3,
                            'text': ' '.join(text_lines)
                        })
                else:
                    i += 1
        except Exception as e:
            logger.debug(f"VTT parse error: {e}")
        
        return captions

    def _parse_vtt_timestamp(self, line: str) -> tuple:
        try:
            parts = line.split('-->')[0].strip().split(':')
            if len(parts) == 2:
                mins = int(parts[0])
                secs = float(parts[1])
            elif len(parts) == 3:
                hours = int(parts[0])
                mins = int(parts[1])
                secs = float(parts[2])
            else:
                return 0, 3
            
            start = mins * 60 + secs
            return start, 3
        except:
            return 0, 3

    async def search_videos(self, query: str, accent: str = "us", max_results: int = 20) -> list:
        accent_query = {
            'us': 'american accent interview',
            'uk': 'british accent bbc interview',
            'au': 'australian accent interview'
        }.get(accent, 'interview')
        
        search_query = f"{query} {accent_query}".strip()
        
        for instance in INVIDIOUS_INSTANCES:
            try:
                url = f"{instance}/api/v1/search?q={search_query}&type=video&max_results={max_results}"
                async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        videos = []
                        for item in data:
                            if item.get('type') == 'video':
                                videos.append({
                                    'id': item.get('videoId'),
                                    'title': item.get('title'),
                                    'channel': item.get('author')
                                })
                        if videos:
                            logger.info(f"Found {len(videos)} videos via {instance}")
                            return videos
            except Exception as e:
                logger.debug(f"Invidious search failed: {e}")
                continue
        
        return self._search_with_ytdlp(search_query, max_results)

    def _search_with_ytdlp(self, query: str, max_results: int) -> list:
        try:
            import yt_dlp
        except ImportError:
            return []
        
        videos = []
        
        opts = {
            'quiet': True,
            'no_warnings': True,
            'default_search': f'ytsearch{max_results}',
            'extract_flat': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
                if info and info.get('entries'):
                    for entry in info['entries']:
                        videos.append({
                            'id': entry.get('id'),
                            'title': entry.get('title'),
                            'channel': entry.get('channel') or entry.get('uploader', 'Unknown')
                        })
        except Exception as e:
            logger.error(f"yt-dlp search failed: {e}")
        
        return videos


youtube_service = YoutubeService()
