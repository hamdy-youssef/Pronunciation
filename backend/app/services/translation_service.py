import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


class TranslationService:
    def __init__(self):
        self.arabic_pattern = re.compile(r'[\u0600-\u06FF\u0750-\u077F]')
        self.english_pattern = re.compile(r'[a-zA-Z]')
        self.en_to_ar_phrases = {
            'how are you': 'كيف حالك',
            'good morning': 'صباح الخير',
            'good evening': 'مساء الخير',
            'thank you': 'شكرا لك',
            'pronunciation': 'النطق',
            'search pronunciation': 'ابحث عن النطق',
            'real youtube videos': 'مقاطع يوتيوب حقيقية',
        }
        self.ar_to_en_phrases = {v: k for k, v in self.en_to_ar_phrases.items()}
        self.en_to_ar_words = {
            'hello': 'مرحبا',
            'hi': 'مرحبا',
            'word': 'كلمة',
            'phrase': 'عبارة',
            'video': 'فيديو',
            'search': 'بحث',
            'learn': 'تعلم',
            'speak': 'يتحدث',
            'native': 'أصلي',
            'better': 'أفضل',
            'clip': 'مقطع',
            'play': 'تشغيل',
            'translate': 'ترجم',
        }
        self.ar_to_en_words = {
            'مرحبا': 'hello',
            'كلمة': 'word',
            'عبارة': 'phrase',
            'فيديو': 'video',
            'بحث': 'search',
            'تعلم': 'learn',
            'يتحدث': 'speaks',
            'أصلي': 'native',
            'أفضل': 'better',
            'مقطع': 'clip',
            'تشغيل': 'play',
            'ترجم': 'translate',
        }

    def detect_language(self, text: str) -> str:
        if not text:
            return 'en'

        arabic_chars = len(self.arabic_pattern.findall(text))
        english_chars = len(self.english_pattern.findall(text))

        if arabic_chars > english_chars:
            return 'ar'
        return 'en'

    def _replace_phrases(self, text: str, mapping: dict) -> str:
        result = text
        for source, target in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
            result = re.sub(rf'\b{re.escape(source)}\b', target, result, flags=re.I)
        return result

    def _translate_words(self, text: str, mapping: dict) -> str:
        tokens = re.findall(r"\w+|\s+|[^\w\s]+", text, flags=re.UNICODE)
        translated = []

        for token in tokens:
            if token.isspace() or re.fullmatch(r'[^\w\s]+', token or ''):
                translated.append(token)
                continue

            translated.append(mapping.get(token.lower(), mapping.get(token, token)))

        return ''.join(translated)

    def _translate_text(self, text: str, target_lang: str) -> str:
        source_lang = self.detect_language(text)
        normalized = text.strip()

        if source_lang == 'en' and target_lang == 'ar':
            phrase_first = self._replace_phrases(normalized, self.en_to_ar_phrases)
            return self._translate_words(phrase_first, self.en_to_ar_words)

        if source_lang == 'ar' and target_lang == 'en':
            phrase_first = self._replace_phrases(normalized, self.ar_to_en_phrases)
            return self._translate_words(phrase_first, self.ar_to_en_words)

        return normalized

    async def translate(self, text: str, target_lang: Optional[str] = None) -> dict:
        detected = self.detect_language(text)

        if not target_lang:
            target_lang = 'ar' if detected == 'en' else 'en'

        if detected == target_lang:
            return {
                'original': text,
                'translated': text,
                'detected_lang': detected,
                'target_lang': target_lang,
            }

        translated_text = self._translate_text(text, target_lang)

        if not translated_text:
            translated_text = text

        return {
            'original': text,
            'translated': translated_text,
            'detected_lang': detected,
            'target_lang': target_lang,
        }


translation_service = TranslationService()
