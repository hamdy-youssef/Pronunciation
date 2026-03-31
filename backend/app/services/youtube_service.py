import httpx
import asyncio
import logging
import json
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

INVIDIOUS_INSTANCES = [
    'https://invidious.projectsegfau.lt',
    'https://invidious.tiekoetter.com',
    'https://vid.puffyan.us',
    'https://iv.ggtyler.dev',
]


class YoutubeService:
    def __init__(self):
        self._session = None

    async def get_session(self) -> httpx.AsyncClient:
        if self._session is None:
            self._session = httpx.AsyncClient(
                timeout=15.0,
                follow_redirects=True,
                headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
            )
        return self._session

    async def close(self):
        if self._session:
            await self._session.aclose()
            self._session = None

    async def get_captions(self, video_id: str) -> list:
        client = await self.get_session()
        
        for instance in INVIDIOUS_INSTANCES:
            try:
                resp = await client.get(f"{instance}/api/v1/captions/{video_id}")
                if resp.status_code == 200:
                    data = resp.json()
                    if data and len(data) > 0:
                        for cap in data:
                            if cap.get('languageCode') == 'en':
                                caption_url = cap.get('url')
                                if caption_url:
                                    return await self._fetch_caption(caption_url, client)
            except Exception as e:
                logger.debug(f"Instance {instance} failed: {e}")
                continue
        
        return await self._get_captions_yt_direct(video_id, client)

    async def _fetch_caption(self, url: str, client: httpx.AsyncClient) -> list:
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                text = resp.text
                if not text or len(text) < 10:
                    return []
                
                if url.endswith('.json3') or 'json3' in url:
                    return self._parse_json3(text)
                elif url.endswith('.srv3') or 'srv3' in url:
                    return self._parse_srv3(text)
                elif url.endswith('.vtt') or 'vtt' in url:
                    return self._parse_vtt(text)
        except Exception as e:
            logger.debug(f"Fetch caption failed: {e}")
        
        return []

    async def _get_captions_yt_direct(self, video_id: str, client: httpx.AsyncClient) -> list:
        urls = [
            f"https://www.youtube.com/api/timedtext?lang=en&v={video_id}&fmt=json3",
            f"https://www.youtube.com/api/timedtext?lang=en&v={video_id}&fmt=srv3",
            f"https://www.youtube.com/api/timedtext?lang=en&v={video_id}&fmt=vtt",
        ]
        
        for url in urls:
            try:
                resp = await client.get(url)
                if resp.status_code == 200 and len(resp.text) > 10:
                    if 'json3' in url:
                        return self._parse_json3(resp.text)
                    elif 'srv3' in url:
                        return self._parse_srv3(resp.text)
                    elif 'vtt' in url:
                        return self._parse_vtt(resp.text)
            except:
                continue
        
        return []

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
            else:
                return 0, 3
            
            start = mins * 60 + secs
            return start, 3
        except:
            return 0, 3

    async def search_videos(self, query: str, accent: str = "us", max_results: int = 20) -> list:
        accent_query = {
            'us': 'american accent',
            'uk': 'british accent bbc',
            'au': 'australian accent'
        }.get(accent, '')
        
        search_query = f"{query} {accent_query}".strip()
        client = await self.get_session()
        
        for instance in INVIDIOUS_INSTANCES:
            try:
                resp = await client.get(
                    f"{instance}/api/v1/search?q={search_query}&type=video&max_results={max_results}"
                )
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
                logger.debug(f"Search failed on {instance}: {e}")
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
