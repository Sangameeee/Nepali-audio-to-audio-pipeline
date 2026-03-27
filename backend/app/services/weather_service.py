# ==============================================================================
# Vani - Weather Service (Open-Meteo)
# File: backend/app/services/weather_service.py
#
# Purpose:
#   Modular weather service using the Open-Meteo API (free, no API key).
#   Handles:
#     - Current weather ("What's the weather in Kathmandu?")
#     - Today's forecast  ("How's the weather today?")
#     - Tomorrow's forecast ("Will it rain tomorrow in Pokhara?")
#     - Multi-day forecast (up to 7 days)
#
# Communication:
#   - Called by: processor.py (_handle_weather)
#   - Uses: Open-Meteo Geocoding API + Open-Meteo Forecast API
#   - Input: city name (str), time frame ("current", "today", "tomorrow")
#   - Output: WeatherResult dataclass with structured weather data
#
# API Endpoints:
#   - Geocoding: https://geocoding-api.open-meteo.com/v1/search
#   - Forecast:  https://api.open-meteo.com/v1/forecast
#
# No API key required.
# ==============================================================================

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Dict

import httpx

logger = logging.getLogger("vani.weather")

# ── Open-Meteo API URLs ─────────────────────────────────────────────────
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# ── WMO Weather Code → Description Mapping ──────────────────────────────
# https://open-meteo.com/en/docs#weathervariables
WMO_WEATHER_CODES: Dict[int, dict] = {
    0:  {"description": "Clear sky",             "simple": "sunny",          "icon": "☀️"},
    1:  {"description": "Mainly clear",          "simple": "mostly sunny",   "icon": "🌤️"},
    2:  {"description": "Partly cloudy",         "simple": "partly cloudy",  "icon": "⛅"},
    3:  {"description": "Overcast",              "simple": "cloudy",         "icon": "☁️"},
    45: {"description": "Foggy",                 "simple": "foggy",          "icon": "🌫️"},
    48: {"description": "Depositing rime fog",   "simple": "foggy",          "icon": "🌫️"},
    51: {"description": "Light drizzle",         "simple": "light drizzle",  "icon": "🌦️"},
    53: {"description": "Moderate drizzle",      "simple": "drizzle",        "icon": "🌦️"},
    55: {"description": "Dense drizzle",         "simple": "heavy drizzle",  "icon": "🌧️"},
    56: {"description": "Light freezing drizzle","simple": "freezing drizzle","icon": "🌧️"},
    57: {"description": "Dense freezing drizzle","simple": "freezing drizzle","icon": "🌧️"},
    61: {"description": "Slight rain",           "simple": "light rain",     "icon": "🌧️"},
    63: {"description": "Moderate rain",         "simple": "rainy",          "icon": "🌧️"},
    65: {"description": "Heavy rain",            "simple": "heavy rain",     "icon": "🌧️"},
    66: {"description": "Light freezing rain",   "simple": "freezing rain",  "icon": "🌧️"},
    67: {"description": "Heavy freezing rain",   "simple": "freezing rain",  "icon": "🌧️"},
    71: {"description": "Slight snow fall",      "simple": "light snow",     "icon": "🌨️"},
    73: {"description": "Moderate snow fall",    "simple": "snowy",          "icon": "🌨️"},
    75: {"description": "Heavy snow fall",       "simple": "heavy snow",     "icon": "❄️"},
    77: {"description": "Snow grains",           "simple": "snow grains",    "icon": "❄️"},
    80: {"description": "Slight rain showers",   "simple": "light showers",  "icon": "🌦️"},
    81: {"description": "Moderate rain showers", "simple": "showers",        "icon": "🌧️"},
    82: {"description": "Violent rain showers",  "simple": "heavy showers",  "icon": "🌧️"},
    85: {"description": "Slight snow showers",   "simple": "light snow showers", "icon": "🌨️"},
    86: {"description": "Heavy snow showers",    "simple": "heavy snow showers", "icon": "🌨️"},
    95: {"description": "Thunderstorm",          "simple": "thunderstorm",   "icon": "⛈️"},
    96: {"description": "Thunderstorm with slight hail", "simple": "thunderstorm with hail", "icon": "⛈️"},
    99: {"description": "Thunderstorm with heavy hail",  "simple": "severe thunderstorm",    "icon": "⛈️"},
}

# ── Time-frame keywords ─────────────────────────────────────────────────
TODAY_KEYWORDS_EN = ["today", "right now", "currently", "current", "now"]
TOMORROW_KEYWORDS_EN = ["tomorrow", "next day"]
TODAY_KEYWORDS_NE = ["आज", "अहिले", "यतिबेला"]
TOMORROW_KEYWORDS_NE = ["भोलि", "भोलिको"]


# ── Data Classes ─────────────────────────────────────────────────────────

@dataclass
class GeoLocation:
    """Geocoded location result."""
    name: str
    country: str
    latitude: float
    longitude: float
    admin1: str = ""  # State / Province
    timezone: str = "auto"


@dataclass
class CurrentWeather:
    """Current weather snapshot."""
    temperature: float
    windspeed: float
    weather_code: int
    description: str
    simple: str
    time: str


@dataclass
class DailyForecast:
    """Single-day forecast."""
    date: str
    temp_max: float
    temp_min: float
    weather_code: int
    description: str
    simple: str
    precipitation_sum: float
    windspeed_max: float


@dataclass
class WeatherResult:
    """Complete weather result returned to the processor."""
    city: str
    country: str
    timeframe: str  # "current", "today", "tomorrow"
    current: Optional[CurrentWeather] = None
    today: Optional[DailyForecast] = None
    tomorrow: Optional[DailyForecast] = None
    daily_forecasts: List[DailyForecast] = field(default_factory=list)
    formatted_response: str = ""


# ── Weather Service ──────────────────────────────────────────────────────

class WeatherService:
    """
    Modular weather service using Open-Meteo API.

    Usage:
        service = WeatherService()
        result = await service.get_weather("Kathmandu", timeframe="today")
        print(result.formatted_response)
    """

    def __init__(self, prefer_country: str = "Nepal", timeout: float = 10.0):
        """
        Args:
            prefer_country: Preferred country when multiple geocoding results match.
            timeout: HTTP request timeout in seconds.
        """
        self.prefer_country = prefer_country
        self._http_client = httpx.AsyncClient(timeout=timeout)
        logger.info("Weather Service initialized (Open-Meteo, no API key required).")

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    async def get_weather(self, city: str, timeframe: str = "current") -> WeatherResult:
        """
        Get weather for a city.

        Args:
            city: City name (e.g., "Kathmandu", "Pokhara").
            timeframe: One of "current", "today", "tomorrow".

        Returns:
            WeatherResult with structured data and a formatted English response.
        """
        # Step 1: Geocode the city
        location = await self._geocode_city(city)
        if not location:
            return WeatherResult(
                city=city,
                country="",
                timeframe=timeframe,
                formatted_response=f"Sorry, I couldn't find a location called '{city}'. Please try a different city name.",
            )

        # Step 2: Fetch forecast data from Open-Meteo
        weather_data = await self._fetch_forecast(location)
        if not weather_data:
            return WeatherResult(
                city=location.name,
                country=location.country,
                timeframe=timeframe,
                formatted_response=f"Sorry, I couldn't retrieve weather data for {location.name}, {location.country}. Please try again later.",
            )

        # Step 3: Parse and build result
        result = self._build_result(location, weather_data, timeframe)
        return result

    def detect_timeframe(self, original_text: str, english_text: str) -> str:
        """
        Detect the time frame from query text.

        Args:
            original_text: Original query (may be Nepali).
            english_text: English version of the query.

        Returns:
            "today", "tomorrow", or "current".
        """
        en_lower = english_text.lower()

        if any(kw in en_lower for kw in TOMORROW_KEYWORDS_EN) or \
           any(kw in original_text for kw in TOMORROW_KEYWORDS_NE):
            return "tomorrow"

        if any(kw in en_lower for kw in TODAY_KEYWORDS_EN) or \
           any(kw in original_text for kw in TODAY_KEYWORDS_NE):
            return "today"

        # Default to current weather
        return "current"

    # ──────────────────────────────────────────────────────────────────────
    # Geocoding
    # ──────────────────────────────────────────────────────────────────────

    async def _geocode_city(self, city_name: str) -> Optional[GeoLocation]:
        """
        Geocode a city name using Open-Meteo Geocoding API.

        Prefers results from self.prefer_country (default: Nepal).

        Args:
            city_name: City to look up.

        Returns:
            GeoLocation or None if not found.
        """
        try:
            params = {"name": city_name, "count": 10, "language": "en", "format": "json"}
            response = await self._http_client.get(GEOCODING_URL, params=params)
            response.raise_for_status()
            data = response.json()

            results = data.get("results", [])
            if not results:
                logger.warning(f"Geocoding: No results for '{city_name}'.")
                return None

            # Prefer the configured country
            preferred = [r for r in results if r.get("country") == self.prefer_country]
            location_data = preferred[0] if preferred else results[0]

            location = GeoLocation(
                name=location_data["name"],
                country=location_data.get("country", ""),
                latitude=location_data["latitude"],
                longitude=location_data["longitude"],
                admin1=location_data.get("admin1", ""),
                timezone=location_data.get("timezone", "auto"),
            )

            logger.info(
                f"Geocoded '{city_name}' → {location.name}, {location.country} "
                f"({location.latitude}, {location.longitude})"
            )
            return location

        except httpx.HTTPStatusError as e:
            logger.error(f"Geocoding HTTP error for '{city_name}': {e}")
            return None
        except Exception as e:
            logger.error(f"Geocoding error for '{city_name}': {e}")
            return None

    # ──────────────────────────────────────────────────────────────────────
    # Forecast Fetching
    # ──────────────────────────────────────────────────────────────────────

    async def _fetch_forecast(self, location: GeoLocation) -> Optional[dict]:
        """
        Fetch weather forecast from Open-Meteo.

        Requests:
          - Current weather
          - Daily forecast (2 days: today + tomorrow) with temperature,
            weather code, precipitation, and wind speed.

        Args:
            location: Geocoded location.

        Returns:
            Raw JSON dict from Open-Meteo, or None on failure.
        """
        try:
            params = {
                "latitude": location.latitude,
                "longitude": location.longitude,
                "current_weather": "true",
                "daily": "temperature_2m_max,temperature_2m_min,weathercode,precipitation_sum,windspeed_10m_max",
                "timezone": location.timezone if location.timezone != "auto" else "auto",
                "forecast_days": 2,
            }
            response = await self._http_client.get(FORECAST_URL, params=params)
            response.raise_for_status()
            data = response.json()

            logger.info(f"Fetched forecast for {location.name}: keys={list(data.keys())}")
            return data

        except httpx.HTTPStatusError as e:
            logger.error(f"Forecast HTTP error: {e}")
            return None
        except Exception as e:
            logger.error(f"Forecast error: {e}")
            return None

    # ──────────────────────────────────────────────────────────────────────
    # Result Building
    # ──────────────────────────────────────────────────────────────────────

    def _build_result(self, location: GeoLocation, data: dict, timeframe: str) -> WeatherResult:
        """
        Parse Open-Meteo response and build a WeatherResult.

        Args:
            location: Geocoded location.
            data: Raw Open-Meteo forecast JSON.
            timeframe: "current", "today", or "tomorrow".

        Returns:
            WeatherResult with populated fields.
        """
        result = WeatherResult(
            city=location.name,
            country=location.country,
            timeframe=timeframe,
        )

        # ── Parse current weather ────────────────────────────────────────
        cw = data.get("current_weather")
        if cw:
            code = cw.get("weathercode", -1)
            code_info = self._decode_weather_code(code)
            result.current = CurrentWeather(
                temperature=cw["temperature"],
                windspeed=cw["windspeed"],
                weather_code=code,
                description=code_info["description"],
                simple=code_info["simple"],
                time=cw.get("time", ""),
            )

        # ── Parse daily forecasts ────────────────────────────────────────
        daily = data.get("daily", {})
        dates = daily.get("time", [])
        temp_maxes = daily.get("temperature_2m_max", [])
        temp_mins = daily.get("temperature_2m_min", [])
        weather_codes = daily.get("weathercode", [])
        precip_sums = daily.get("precipitation_sum", [])
        wind_maxes = daily.get("windspeed_10m_max", [])

        for i, date in enumerate(dates):
            code = weather_codes[i] if i < len(weather_codes) else -1
            code_info = self._decode_weather_code(code)
            forecast = DailyForecast(
                date=date,
                temp_max=temp_maxes[i] if i < len(temp_maxes) else 0,
                temp_min=temp_mins[i] if i < len(temp_mins) else 0,
                weather_code=code,
                description=code_info["description"],
                simple=code_info["simple"],
                precipitation_sum=precip_sums[i] if i < len(precip_sums) else 0,
                windspeed_max=wind_maxes[i] if i < len(wind_maxes) else 0,
            )
            result.daily_forecasts.append(forecast)

            if i == 0:
                result.today = forecast
            elif i == 1:
                result.tomorrow = forecast

        # ── Format response string ───────────────────────────────────────
        result.formatted_response = self._format_response(result, timeframe)
        return result

    def _format_response(self, result: WeatherResult, timeframe: str) -> str:
        """
        Generate a natural English response based on weather data and timeframe.

        Args:
            result: Populated WeatherResult.
            timeframe: "current", "today", or "tomorrow".

        Returns:
            Formatted English weather string.
        """
        city_label = f"{result.city}, {result.country}" if result.country else result.city

        if timeframe == "current" and result.current:
            cw = result.current
            response = (
                f"Current weather in {city_label}: {cw.description} ({cw.simple}). "
                f"Temperature: {cw.temperature}°C. "
                f"Wind speed: {cw.windspeed} km/h."
            )
            # Also include today's high/low if available
            if result.today:
                response += (
                    f" Today's forecast: High of {result.today.temp_max}°C, "
                    f"Low of {result.today.temp_min}°C."
                )
            return response

        elif timeframe == "today" and result.today:
            day = result.today
            response = (
                f"Today's weather in {city_label}: It will be {day.simple} ({day.description}). "
                f"High: {day.temp_max}°C, Low: {day.temp_min}°C. "
                f"Max wind speed: {day.windspeed_max} km/h."
            )
            if day.precipitation_sum > 0:
                response += f" Expected precipitation: {day.precipitation_sum} mm."
            else:
                response += " No significant precipitation expected."
            # Include current conditions for context
            if result.current:
                response += (
                    f" Right now it is {result.current.temperature}°C "
                    f"and {result.current.simple}."
                )
            return response

        elif timeframe == "tomorrow" and result.tomorrow:
            day = result.tomorrow
            response = (
                f"Tomorrow's weather in {city_label}: It is expected to be {day.simple} ({day.description}). "
                f"High: {day.temp_max}°C, Low: {day.temp_min}°C. "
                f"Max wind speed: {day.windspeed_max} km/h."
            )
            if day.precipitation_sum > 0:
                response += f" Expected precipitation: {day.precipitation_sum} mm."
            else:
                response += " No significant precipitation expected."
            return response

        # Fallback: if we have current weather at least
        if result.current:
            cw = result.current
            return (
                f"Weather in {city_label}: {cw.description}, {cw.temperature}°C, "
                f"wind {cw.windspeed} km/h."
            )

        return f"Sorry, I couldn't get detailed weather information for {city_label}."

    # ──────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _decode_weather_code(code: int) -> dict:
        """
        Decode a WMO weather code into description and simple label.

        Args:
            code: WMO weather interpretation code.

        Returns:
            dict with "description" and "simple" keys.
        """
        return WMO_WEATHER_CODES.get(code, {
            "description": "Unknown",
            "simple": "unknown conditions",
            "icon": "❓",
        })

    async def cleanup(self):
        """Close the HTTP client."""
        await self._http_client.aclose()
        logger.info("Weather Service cleaned up.")
