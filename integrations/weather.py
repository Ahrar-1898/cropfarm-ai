import math
import os
import ssl
import threading
import time

import requests


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT = 8
CACHE_SECONDS = 900

WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}

_weather_cache = {}
_cache_lock = threading.Lock()


class WeatherIntegrationError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _request_json(url, params):
    configured_bundle = os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("CURL_CA_BUNDLE")
    system_bundle = ssl.get_default_verify_paths().cafile
    verify_bundle = configured_bundle or (
        system_bundle if system_bundle and os.path.isfile(system_bundle) else True
    )
    try:
        response = requests.get(
            url,
            params=params,
            headers={"User-Agent": "CropFarmAI/1.0"},
            timeout=REQUEST_TIMEOUT,
            verify=verify_bundle,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as error:
        raise WeatherIntegrationError("provider_unavailable") from error
    if not isinstance(payload, dict):
        raise WeatherIntegrationError("invalid_provider_response")
    return payload


def _number(value, *, optional=False):
    if value is None and optional:
        return None
    if isinstance(value, bool):
        raise WeatherIntegrationError("invalid_provider_response")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise WeatherIntegrationError("invalid_provider_response") from error
    if not math.isfinite(number):
        raise WeatherIntegrationError("invalid_provider_response")
    return number


def _condition(code):
    if isinstance(code, bool):
        return "Unknown conditions"
    try:
        return WEATHER_CODES.get(int(code), "Unknown conditions")
    except (TypeError, ValueError):
        return "Unknown conditions"


def _fetch_weather_report(location):
    geocoding = _request_json(
        GEOCODING_URL,
        {"name": location, "count": 1, "language": "en", "format": "json"},
    )
    results = geocoding.get("results")
    if not isinstance(results, list) or not results:
        raise WeatherIntegrationError("location_not_found")
    place = results[0]
    if not isinstance(place, dict):
        raise WeatherIntegrationError("invalid_provider_response")
    latitude = _number(place.get("latitude"))
    longitude = _number(place.get("longitude"))
    forecast = _request_json(
        FORECAST_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,"
                "precipitation,weather_code,wind_speed_10m,is_day"
            ),
            "daily": (
                "weather_code,precipitation_probability_max,precipitation_sum,"
                "et0_fao_evapotranspiration"
            ),
            "timezone": "auto",
            "forecast_days": 7,
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
        },
    )
    current = forecast.get("current")
    daily = forecast.get("daily")
    if not isinstance(current, dict) or not isinstance(daily, dict):
        raise WeatherIntegrationError("invalid_provider_response")

    daily_dates = daily.get("time")
    daily_codes = daily.get("weather_code")
    daily_probabilities = daily.get("precipitation_probability_max")
    daily_precipitation = daily.get("precipitation_sum")
    daily_et0 = daily.get("et0_fao_evapotranspiration")
    arrays = (daily_dates, daily_codes, daily_probabilities, daily_precipitation, daily_et0)
    if not all(isinstance(values, list) for values in arrays):
        raise WeatherIntegrationError("invalid_provider_response")
    if len({len(values) for values in arrays}) != 1 or not daily_dates:
        raise WeatherIntegrationError("invalid_provider_response")

    current_data = {
        "time": current.get("time"),
        "temperature_c": _number(current.get("temperature_2m")),
        "apparent_temperature_c": _number(current.get("apparent_temperature")),
        "humidity_pct": _number(current.get("relative_humidity_2m")),
        "precipitation_mm": _number(current.get("precipitation")),
        "wind_speed_kmh": _number(current.get("wind_speed_10m")),
        "condition": _condition(current.get("weather_code")),
        "is_day": bool(current.get("is_day")),
    }
    if not isinstance(current_data["time"], str):
        raise WeatherIntegrationError("invalid_provider_response")

    forecast_days = []
    for index, forecast_date in enumerate(daily_dates):
        if not isinstance(forecast_date, str):
            raise WeatherIntegrationError("invalid_provider_response")
        forecast_days.append(
            {
                "date": forecast_date,
                "condition": _condition(daily_codes[index]),
                "precipitation_probability_pct": _number(
                    daily_probabilities[index], optional=True
                ),
                "precipitation_mm": _number(daily_precipitation[index], optional=True),
                "et0_mm": _number(daily_et0[index], optional=True),
            }
        )

    place_name = place.get("name")
    if not isinstance(place_name, str) or not place_name.strip():
        raise WeatherIntegrationError("invalid_provider_response")
    country = place.get("country")
    display_location = f"{place_name}, {country}" if country else place_name
    return {
        "provider": "Open-Meteo",
        "location": display_location,
        "timezone": forecast.get("timezone"),
        "current": current_data,
        "forecast": forecast_days,
    }


def get_weather_report(location):
    normalized_location = location.strip() if isinstance(location, str) else ""
    if not normalized_location:
        raise WeatherIntegrationError("location_required")
    if len(normalized_location) > 120:
        raise WeatherIntegrationError("invalid_location")

    cache_key = normalized_location.casefold()
    now = time.monotonic()
    with _cache_lock:
        cached = _weather_cache.get(cache_key)
        if cached and now - cached[0] < CACHE_SECONDS:
            return cached[1]

    report = _fetch_weather_report(normalized_location)
    with _cache_lock:
        _weather_cache[cache_key] = (time.monotonic(), report)
    return report


def get_irrigation_advisory(weather_report):
    forecast = weather_report["forecast"]
    measurable_rain = [
        day
        for day in forecast[:3]
        if day["precipitation_mm"] is not None and day["precipitation_mm"] >= 1
    ]
    if measurable_rain:
        rainy_day = measurable_rain[0]
        summary = (
            f"Rain is forecast on {rainy_day['date']} "
            f"({rainy_day['precipitation_mm']:g} mm). Review your planned irrigation "
            "against field conditions."
        )
    elif forecast and all(
        day["precipitation_mm"] is not None and day["precipitation_mm"] < 1
        for day in forecast
    ):
        summary = (
            "Little or no rainfall is forecast for the next seven days. Check soil "
            "moisture and crop stage before planning watering."
        )
    else:
        summary = (
            "The rainfall forecast is mixed or incomplete. Check field soil moisture "
            "and local crop guidance before planning watering."
        )
    return {
        "summary": summary,
        "basis": "Weather context only; not a crop-specific watering recommendation.",
    }
