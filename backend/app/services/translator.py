# ==============================================================================
# Vani - Translation Service
# File: backend/app/services/translator.py
#
# Purpose:
#   Handles bidirectional translation between English and Nepali
#   using deep-translator (Google Translate API wrapper).
#
# Communication:
#   - Called by: routers/query.py and services/processor.py
#   - Input: text (str) + source_lang + target_lang
#   - Output: translated text (str)
# ==============================================================================

import logging

from deep_translator import GoogleTranslator

from app.config import Settings

logger = logging.getLogger("vani.translator")


class TranslatorService:
    """
    Translation service for English <-> Nepali using deep-translator.
    """

    def __init__(self, settings: Settings):
        """
        Args:
            settings: App settings containing model names/paths.
        """
        self.settings = settings
        self._en_to_ne = GoogleTranslator(source="en", target="ne")
        self._ne_to_en = GoogleTranslator(source="ne", target="en")
        logger.info("Translator Service initialized (deep-translator).")

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """
        Translate text between English and Nepali.

        Args:
            text: Input text to translate.
            source_lang: Source language ("en" or "ne").
            target_lang: Target language ("en" or "ne").

        Returns:
            Translated text string. If source == target, returns original text.
        """
        if source_lang == target_lang:
            return text

        if not text or not text.strip():
            return text

        if source_lang == "en" and target_lang == "ne":
            return await self._translate_en_to_ne(text)
        elif source_lang == "ne" and target_lang == "en":
            return await self._translate_ne_to_en(text)
        else:
            logger.warning(f"Unsupported translation pair: {source_lang} → {target_lang}")
            return text

    async def _translate_en_to_ne(self, text: str) -> str:
        """
        Translate English text to Nepali using deep-translator.

        Args:
            text: English input text.
        Returns:
            Nepali translated text.
        """
        try:
            translated = self._en_to_ne.translate(text)
            logger.info(f"Translated EN→NE: '{text[:60]}...' → '{translated[:60]}...'")
            return translated
        except Exception as e:
            logger.error(f"EN→NE translation error: {e}")
            # Retry with a fresh translator instance
            try:
                self._en_to_ne = GoogleTranslator(source="en", target="ne")
                return self._en_to_ne.translate(text)
            except Exception as retry_e:
                logger.error(f"EN→NE translation retry failed: {retry_e}")
                return f"[Translation Error] {text}"

    async def _translate_ne_to_en(self, text: str) -> str:
        """
        Translate Nepali text to English using deep-translator.

        Args:
            text: Nepali input text.
        Returns:
            English translated text.
        """
        try:
            translated = self._ne_to_en.translate(text)
            logger.info(f"Translated NE→EN: '{text[:60]}...' → '{translated[:60]}...'")
            return translated
        except Exception as e:
            logger.error(f"NE→EN translation error: {e}")
            # Retry with a fresh translator instance
            try:
                self._ne_to_en = GoogleTranslator(source="ne", target="en")
                return self._ne_to_en.translate(text)
            except Exception as retry_e:
                logger.error(f"NE→EN translation retry failed: {retry_e}")
                return f"[Translation Error] {text}"

    def cleanup(self):
        """Release resources."""
        logger.info("Translator Service cleaned up.")
