import re
import logging

logger = logging.getLogger(__name__)


class TranscriptService:
    @staticmethod
    def process_captions(captions: list) -> list:
        processed = []
        
        for cap in captions:
            text = cap.get('text', '')
            if not text or not text.strip():
                continue
            
            cleaned_text = TranscriptService._clean_text(text)
            
            if cleaned_text:
                processed.append({
                    'videoId': cap.get('videoId'),
                    'text': cleaned_text,
                    'original_text': text,
                    'timestamp': cap.get('start', 0),
                    'duration': cap.get('duration', 0)
                })
        
        return processed

    @staticmethod
    def _clean_text(text: str) -> str:
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        return text

    @staticmethod
    def split_sentences(captions: list) -> list:
        sentences = []
        
        current_sentence = []
        current_start = None
        
        for cap in captions:
            text = cap.get('text', '')
            
            if not text:
                continue
            
            current_sentence.append(text)
            
            if '.' in text or '?' in text or '!' in text or len(current_sentence) >= 3:
                if current_sentence:
                    combined = ' '.join(current_sentence)
                    sentences.append({
                        'videoId': cap.get('videoId'),
                        'text': combined,
                        'timestamp': current_start if current_start is not None else cap.get('timestamp', 0),
                        'duration': cap.get('duration', 0)
                    })
                    current_sentence = []
                    current_start = None
            else:
                if current_start is None:
                    current_start = cap.get('timestamp', 0)
        
        if current_sentence:
            combined = ' '.join(current_sentence)
            sentences.append({
                'videoId': captions[-1].get('videoId'),
                'text': combined,
                'timestamp': current_start if current_start is not None else 0,
                'duration': 0
            })
        
        return sentences


transcript_service = TranscriptService()
