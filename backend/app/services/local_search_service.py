import json
import logging
import os
import random
import re
from difflib import SequenceMatcher
from typing import Optional

logger = logging.getLogger(__name__)

DATA_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'transcripts.json')
NOISE_PATTERNS = re.compile(r'\[(music|applause|laughter|noise|intro|outro)\]|^(music|applause|laughter)$', re.I)


class LocalSearchService:
    def __init__(self):
        self.transcripts = []
        self.entries = []
        self._load_data()

    def _load_data(self):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.transcripts = data.get('transcripts', [])
                self.entries = self._build_entries(self.transcripts)
                logger.info('Loaded %s transcripts and %s captions', len(self.transcripts), len(self.entries))
        except Exception as e:
            logger.error('Failed to load transcripts: %s', e)
            self.transcripts = []
            self.entries = []

    def _build_entries(self, transcripts: list) -> list:
        entries = []

        for video in transcripts:
            accent = self._infer_accent(video)
            captions = sorted(video.get('captions', []), key=lambda item: item.get('start', 0))

            for index, cap in enumerate(captions):
                text = (cap.get('text') or '').strip()
                if not text or NOISE_PATTERNS.search(text):
                    continue

                start = float(cap.get('start', 0) or 0)
                next_start = float(captions[index + 1].get('start', start + 3.5) or (start + 3.5)) if index + 1 < len(captions) else start + 3.5
                duration = max(1.0, round(next_start - start, 2))

                entries.append({
                    'videoId': video.get('videoId'),
                    'videoTitle': video.get('title', ''),
                    'channel': video.get('channel', ''),
                    'language': video.get('language', 'en'),
                    'accent': accent,
                    'text': text,
                    'subtitle_text': text,
                    'clean_text': self._normalize(text),
                    'timestamp': start,
                    'duration': duration,
                    'caption_index': index,
                })

        return entries

    @staticmethod
    def _infer_accent(video: dict) -> str:
        haystack = ' '.join([
            str(video.get('title', '')),
            str(video.get('channel', '')),
            str(video.get('accent', '')),
        ]).lower()

        if any(token in haystack for token in ('bbc', 'queen', 'adele', 'warren buffett', 'business insider')):
            return 'uk'
        if any(token in haystack for token in ('luis fonsi', 'despacito')):
            return 'es'
        if any(token in haystack for token in ('stanford', 'tesla', 'obama', 'ted', 'ellen', 'jawed')):
            return 'us'
        return video.get('accent', 'us')

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.lower()
        text = re.sub(r"[^\w\s]", ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _score(self, query: str, entry: dict, mode: str = 'smart') -> float:
        normalized_query = self._normalize(query)
        normalized_text = entry.get('clean_text', '')

        if not normalized_query or not normalized_text:
            return 0.0

        if normalized_query == normalized_text:
            return 100.0

        if mode == 'exact':
            return 92.0 if re.search(rf'\b{re.escape(normalized_query)}\b', normalized_text) else 0.0

        if mode == 'phrase':
            if normalized_query in normalized_text:
                return 88.0 + (5.0 if normalized_text.startswith(normalized_query) else 0.0)
            return 0.0

        score = 0.0

        if normalized_query in normalized_text:
            score += 45.0

        if normalized_text in normalized_query:
            score += 18.0

        query_words = set(normalized_query.split())
        text_words = set(normalized_text.split())
        if query_words:
            overlap = len(query_words & text_words) / len(query_words)
            score += overlap * 25.0

        score += SequenceMatcher(None, normalized_query, normalized_text).ratio() * 20.0

        if normalized_text.startswith(normalized_query):
            score += 5.0

        if len(normalized_query.split()) > 1 and normalized_query.replace(' ', '') == normalized_text.replace(' ', ''):
            score += 6.0

        return round(score, 3)

    def search(self, query: str, accent: str = 'all', max_results: int = 50, mode: str = 'smart', randomize: bool = False) -> list:
        if not query:
            return []

        ranked = []
        for entry in self.entries:
            if accent not in ('all', '', None) and entry.get('accent') != accent:
                continue

            score = self._score(query, entry, mode=mode)
            if score <= 0:
                continue

            ranked.append({
                'videoId': entry['videoId'],
                'timestamp': entry['timestamp'],
                'duration': entry['duration'],
                'sentence': entry['text'],
                'subtitleText': entry['subtitle_text'],
                'video_title': entry['videoTitle'],
                'video_channel': entry['channel'],
                'language': entry['language'],
                'accent': entry['accent'],
                'matchType': mode,
                'score': score,
            })

        ranked.sort(key=lambda item: (-item['score'], item['timestamp']))
        if randomize:
            top_slice = ranked[:max_results * 3]
            random.shuffle(top_slice)
            ranked = top_slice + ranked[max_results * 3:]
        return ranked[:max_results]

    def search_best(self, query: str, accent: str = 'all', mode: str = 'smart', randomize: bool = False) -> Optional[dict]:
        results = self.search(query, accent=accent, max_results=1, mode=mode, randomize=randomize)
        if not results:
            return None

        best = results[0]
        best['context'] = self.get_context(best['videoId'], best['timestamp'])
        best['subtitleCues'] = best['context']
        best['subtitleTranscript'] = self.get_transcript_text(best['videoId'])
        return best

    def get_context(self, video_id: str, timestamp: float, window: int = 2) -> list:
        matched = [entry for entry in self.entries if entry.get('videoId') == video_id]
        matched.sort(key=lambda item: item.get('timestamp', 0))

        if not matched:
            return []

        closest_index = 0
        closest_delta = abs(matched[0].get('timestamp', 0) - timestamp)

        for index, entry in enumerate(matched):
            delta = abs(entry.get('timestamp', 0) - timestamp)
            if delta < closest_delta:
                closest_delta = delta
                closest_index = index

        start = max(0, closest_index - max(0, int(window)))
        end = min(len(matched), closest_index + max(0, int(window)) + 1)

        context = [
            {
                'videoId': item['videoId'],
                'timestamp': item['timestamp'],
                'duration': item['duration'],
                'sentence': item['text'],
                'subtitleText': item['subtitle_text'],
                'video_title': item['videoTitle'],
                'video_channel': item['channel'],
            }
            for item in matched[start:end]
        ]

        for item in context:
            item['isMatch'] = abs(item['timestamp'] - timestamp) < 0.001

        return context

    def get_transcript(self, video_id: str) -> Optional[dict]:
        transcript = next((video for video in self.transcripts if video.get('videoId') == video_id), None)
        if not transcript:
            return None

        captions = sorted(transcript.get('captions', []), key=lambda item: item.get('start', 0))
        cleaned_captions = []

        for index, cap in enumerate(captions):
            text = (cap.get('text') or '').strip()
            if not text or NOISE_PATTERNS.search(text):
                continue

            start = float(cap.get('start', 0) or 0)
            next_start = float(captions[index + 1].get('start', start + 3.5) or (start + 3.5)) if index + 1 < len(captions) else start + 3.5
            duration = max(1.0, round(next_start - start, 2))

            cleaned_captions.append({
                'videoId': transcript.get('videoId'),
                'timestamp': start,
                'duration': duration,
                'sentence': text,
                'subtitleText': text,
                'video_title': transcript.get('title', ''),
                'video_channel': transcript.get('channel', ''),
                'language': transcript.get('language', 'en'),
                'accent': self._infer_accent(transcript),
            })

        return {
            'videoId': transcript.get('videoId'),
            'title': transcript.get('title', ''),
            'channel': transcript.get('channel', ''),
            'language': transcript.get('language', 'en'),
            'accent': self._infer_accent(transcript),
            'captionCount': len(cleaned_captions),
            'subtitleTranscript': ' '.join(item['sentence'] for item in cleaned_captions),
            'captions': cleaned_captions,
        }

    def get_transcript_text(self, video_id: str) -> str:
        transcript = self.get_transcript(video_id)
        if not transcript:
            return ''
        return transcript.get('subtitleTranscript', '')

    def get_stats(self) -> dict:
        return {
            'videos': len(self.transcripts),
            'captions': len(self.entries),
            'uniqueWords': len(self.get_all_words()),
        }

    def get_all_words(self) -> list:
        words = set()
        for entry in self.entries:
            for word in entry.get('clean_text', '').split():
                if len(word) > 2:
                    words.add(word)
        return sorted(words)[:100]


local_search_service = LocalSearchService()
