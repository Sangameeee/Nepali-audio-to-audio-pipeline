# ==============================================================================
# Voice Assistant - Query Processor Service
# File: backend/app/services/processor.py
#
# Purpose:
#   Central logic for processing user queries. Determines user intent
#   (weather, news/Q&A, time, general) and routes to the appropriate handler.
#
# Communication:
#   - Called by: routers/query.py
#   - Calls:
#     - weather_service.py for weather queries
#     - Remote RAG+SLM API (Colab + ngrok) for news and general Q&A
#   - Input: query text (str) + source language ("en" or "ne")
#   - Output: dict {"answer_english": str, "steps": list[str], "rag_sources": list}
# ==============================================================================

import logging
import re
import time as time_module
from datetime import datetime
from typing import Optional, TYPE_CHECKING

import httpx
import requests

from app.config import Settings

if TYPE_CHECKING:
    from app.services.weather_service import WeatherService

logger = logging.getLogger("voice_assistant.processor")

# ── Intent Keywords ──────────────────────────────────────────────────────
WEATHER_KEYWORDS_EN = [
    "weather", "temperature", "rain", "forecast", "humidity",
    "wind", "sunny", "cloudy", "storm", "snow", "hot", "cold",
    "climate", "degrees"
]
WEATHER_KEYWORDS_NE = [
    "मौसम", "तापक्रम", "वर्षा", "पूर्वानुमान", "हावा",
    "गर्मी", "चिसो", "बादल"
]

TIME_KEYWORDS_EN = ["time", "clock", "hour", "what time"]
TIME_KEYWORDS_NE = ["समय", "बजे", "घडी", "कति बज्यो"]

# ── City extraction helpers ──────────────────────────────────────────────
KNOWN_CITIES = [
    "kathmandu", "pokhara", "biratnagar", "lalitpur", "bharatpur",
    "birgunj", "dharan", "butwal", "hetauda", "janakpur",
    "new york", "london", "tokyo", "delhi", "mumbai", "sydney",
    "los angeles", "san francisco", "chicago", "seattle", "paris"
]

NEPALI_CITY_MAP = {
    "काठमाडौं": "Kathmandu",
    "काठमाण्डु": "Kathmandu",
    "काठमाण्डौ": "Kathmandu",
    "पोखरा": "Pokhara",
    "विराटनगर": "Biratnagar",
    "ललितपुर": "Lalitpur",
    "भरतपुर": "Bharatpur",
    "वीरगञ्ज": "Birgunj",
    "धरान": "Dharan",
    "बुटवल": "Butwal",
    "हेटौंडा": "Hetauda",
    "जनकपुर": "Janakpur",
    "दिल्ली": "Delhi",
    "मुम्बई": "Mumbai",
    "लण्डन": "London",
    "टोकियो": "Tokyo",
}


class ProcessorService:
    """
    Query processing service.
    Determines intent and generates responses.
    Uses remote RAG+SLM API for news and general Q&A.
    """

    def __init__(self, settings: Settings, weather_service: "WeatherService" = None):
        """
        Args:
            settings: App settings (API keys, RAG URLs, etc.)
            weather_service: Injected WeatherService instance for weather queries.
        """
        self.settings = settings
        self.weather_service = weather_service
        self._http_client = httpx.AsyncClient(timeout=10.0)

        # RAG+SLM API configuration
        self._rag_api_url = settings.RAG_COLAB_API_URL
        self._rag_min_cosine = settings.RAG_MIN_COSINE
        self._rag_days_filter = settings.RAG_DAYS_FILTER
        self._rag_top_k = settings.RAG_TOP_K

        logger.info(
            f"Processor Service initialized (rag_url={self._rag_api_url})."
        )

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    async def process_query(
        self,
        text: str,
        source_lang: str,
        english_text: Optional[str] = None,
    ) -> dict:
        """
        Main entry point for query processing.

        Args:
            text: Original query text (in source language).
            source_lang: Language of the query ("en" or "ne").
            english_text: English translation of the query (if source is Nepali).

        Returns:
            dict: {
                "answer_english": str,
                "intent": str,
                "steps": list[str],
                "rag_sources": list[dict]  (only for RAG queries)
            }
        """
        steps = []
        rag_sources = []
        query_for_processing = english_text if english_text else text

        # ── Intent Detection ─────────────────────────────────────────────
        intent = self._detect_intent(text, query_for_processing, source_lang)
        steps.append(f"Detected intent: {intent}")
        logger.info(f"Detected intent: {intent} for query: '{text[:80]}...'")

        # ── Route to Handler ─────────────────────────────────────────────
        if intent == "weather":
            answer = await self._handle_weather(
                text, query_for_processing, source_lang
            )
            steps.append("Fetched weather data from Open-Meteo.")

        elif intent == "time":
            answer = self._handle_time(text, query_for_processing, source_lang)
            steps.append("Retrieved current time.")

        else:
            # Use RAG+SLM for both news and general queries
            answer, rag_sources = await self._handle_rag_query(
                query_for_processing
            )
            steps.append("Queried RAG+SLM system.")

        return {
            "answer_english": answer,
            "intent": intent,
            "steps": steps,
            "rag_sources": rag_sources,
        }

    # ──────────────────────────────────────────────────────────────────────
    # Intent Detection
    # ──────────────────────────────────────────────────────────────────────

    def _detect_intent(
        self, original_text: str, english_text: str, source_lang: str
    ) -> str:
        """
        Detect user intent using keyword matching.

        Returns: "weather", "time", or "general"
        """
        text_lower = original_text.lower()
        en_lower = english_text.lower()

        # Check weather intent
        if any(kw in en_lower for kw in WEATHER_KEYWORDS_EN) or \
           any(kw in original_text for kw in WEATHER_KEYWORDS_NE):
            return "weather"

        # Check time intent
        if any(kw in en_lower for kw in TIME_KEYWORDS_EN) or \
           any(kw in original_text for kw in TIME_KEYWORDS_NE):
            return "time"

        # Everything else goes to RAG+SLM
        return "general"

    # ──────────────────────────────────────────────────────────────────────
    # Intent Handlers
    # ──────────────────────────────────────────────────────────────────────

    async def _handle_weather(
        self, original_text: str, english_text: str, source_lang: str
    ) -> str:
        """
        Handle weather queries using the Open-Meteo WeatherService.
        """
        city = self._extract_city(original_text, english_text, source_lang)
        if not city:
            city = "Kathmandu"

        if not self.weather_service:
            from app.services.weather_service import WeatherService
            self.weather_service = WeatherService(
                prefer_country=getattr(
                    self.settings, "WEATHER_PREFER_COUNTRY", "Nepal"
                )
            )

        timeframe = self.weather_service.detect_timeframe(
            original_text, english_text
        )
        logger.info(f"Weather query: city='{city}', timeframe='{timeframe}'")

        try:
            result = await self.weather_service.get_weather(
                city, timeframe=timeframe
            )
            return result.formatted_response
        except Exception as e:
            logger.error(f"Weather service error: {e}")
            return (
                f"Sorry, I couldn't fetch weather data for {city}. "
                "Please try again later."
            )

    def _handle_time(
        self, original_text: str, english_text: str, source_lang: str
    ) -> str:
        """Handle time queries using Python's time library."""
        now = datetime.now()
        current_time = now.strftime("%I:%M %p")
        current_date = now.strftime("%B %d, %Y")
        day_of_week = now.strftime("%A")

        return (
            f"The current time is {current_time} on "
            f"{day_of_week}, {current_date}."
        )

    async def _handle_rag_query(
        self, english_text: str
    ) -> tuple[str, list[dict]]:
        """
        Handle queries using the remote RAG+SLM API (Colab + ngrok).

        Sends the question to the RAG server and returns the answer with sources.

        Args:
            english_text: Query in English.
        Returns:
            Tuple of (answer_string, list_of_source_dicts)
        """
        ask_url = f"{self._rag_api_url.rstrip('/')}/ask"

        payload = {
            "question": english_text,
            "min_cosine": self._rag_min_cosine,
            "days_filter": self._rag_days_filter,
            "top_k": self._rag_top_k,
        }

        try:
            response = requests.post(ask_url, json=payload, timeout=120)

            if response.status_code == 200:
                data = response.json()

                # No relevant articles found
                if data.get("answer") is None:
                    message = data.get(
                        "message", "No information found."
                    )
                    logger.info(f"RAG returned no answer: {message}")
                    return message, []

                answer = self._normalize_answer_text(data["answer"])
                sources = data.get("sources", [])

                logger.info(
                    f"RAG answer: '{answer[:80]}...' "
                    f"({len(sources)} sources)"
                )

                return answer, sources
            else:
                detail = response.json().get("detail", response.text)
                logger.error(
                    f"RAG server error {response.status_code}: {detail}"
                )
                return f"Q&A Error: {detail}", []

        except requests.exceptions.Timeout:
            logger.error("RAG request timed out.")
            return (
                "The Q&A system timed out. "
                "Please try again with a simpler question."
            ), []
        except requests.exceptions.ConnectionError:
            logger.error(
                f"Cannot reach RAG server at {self._rag_api_url}"
            )
            return (
                "Cannot reach the Q&A server. "
                "Make sure the Colab notebook is running and the "
                "ngrok URL is up to date."
            ), []
        except Exception as e:
            logger.error(f"Unexpected RAG error: {e}")
            return f"Q&A Error: {str(e)}", []

    def _normalize_answer_text(self, text: str) -> str:
        """Clean model output labels like 'Response:' from the start."""
        if not text:
            return ""
        return re.sub(r"^\s*response\s*:\s*", "", text, flags=re.IGNORECASE).strip()

    # ──────────────────────────────────────────────────────────────────────
    # Utility Methods
    # ──────────────────────────────────────────────────────────────────────

    def _extract_city(
        self, original_text: str, english_text: str, source_lang: str
    ) -> str:
        """Extract a city name from the query text."""
        # Check Nepali city names
        if source_lang == "ne":
            for nepali_name, english_name in NEPALI_CITY_MAP.items():
                if nepali_name in original_text:
                    return english_name

        # Check known English cities
        en_lower = english_text.lower()
        for city in KNOWN_CITIES:
            if city in en_lower:
                return city.title()

        # Try to extract city after "in" or "of"
        for preposition in ["in ", "of ", "at ", "for "]:
            if preposition in en_lower:
                after = en_lower.split(preposition)[-1].strip()
                words = after.split()
                if words:
                    candidate = " ".join(words[:2]).strip("?.!,")
                    if candidate and len(candidate) > 1:
                        return candidate.title()

        return "Kathmandu"

    async def cleanup(self):
        """Close HTTP client and release resources."""
        await self._http_client.aclose()
        logger.info("Processor Service cleaned up.")
