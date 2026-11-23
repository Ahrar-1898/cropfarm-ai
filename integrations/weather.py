import math
import os
import ssl
import threading
import time

import requests


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
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


def _weather_icon(code):
    if isinstance(code, bool):
        return "☁"
    try:
        value = int(code)
    except (TypeError, ValueError):
        return "☁"
    if value == 0:
        return "☀"
    if value in (1, 2):
        return "⛅"
    if value == 3:
        return "☁"
    if value in (45, 48):
        return "🌫"
    if value in (51, 53, 55, 56, 57, 61, 63, 66, 80, 81):
        return "🌦"
    if value in (65, 67, 82):
        return "🌧"
    if value in (71, 73, 75, 77, 85, 86):
        return "❄"
    if value in (95, 96, 99):
        return "⛈"
    return "☁"


def _expanded_location(location):
    expanded = location.strip()
    replacements = (
        (r"\bUP\b", "Uttar Pradesh"),
        (r"\bNCR\b", "National Capital Region"),
        (r"\bU.P.\b", "Uttar Pradesh"),
    )
    for pattern, replacement in replacements:
        import re
        expanded = re.sub(pattern, replacement, expanded, flags=re.IGNORECASE)
    if "india" not in expanded.casefold():
        expanded = f"{expanded}, India"
    return expanded


def resolve_location(location):
    normalized_location = location.strip() if isinstance(location, str) else ""
    if not normalized_location:
        raise WeatherIntegrationError("location_required")
    if len(normalized_location) > 120:
        raise WeatherIntegrationError("invalid_location")
    if len(normalized_location) < 3:
        raise WeatherIntegrationError("invalid_location")

    attempts = [normalized_location]
    expanded = _expanded_location(normalized_location)
    if expanded.casefold() != normalized_location.casefold():
        attempts.append(expanded)

    for attempt in attempts:
        try:
            geocoding = _request_json(
                GEOCODING_URL,
                {"name": attempt, "count": 5, "language": "en", "format": "json"},
            )
        except WeatherIntegrationError:
            geocoding = {}
        results = geocoding.get("results")
        if not isinstance(results, list) or not results:
            try:
                response = requests.get(
                    NOMINATIM_URL,
                    params={
                        "q": attempt,
                        "format": "jsonv2",
                        "addressdetails": 1,
                        "limit": 5,
                        "countrycodes": "in",
                    },
                    headers={"User-Agent": "CropFarmAI/1.0"},
                    timeout=REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                fallback_results = response.json()
            except (requests.RequestException, ValueError) as error:
                raise WeatherIntegrationError("provider_unavailable") from error
            if not isinstance(fallback_results, list) or not fallback_results:
                continue
            candidates = []
            for result in fallback_results:
                if not isinstance(result, dict):
                    continue
                address = result.get("address") if isinstance(result.get("address"), dict) else {}
                candidates.append({
                    "name": result.get("name") or address.get("state_district") or address.get("county") or address.get("city"),
                    "latitude": result.get("lat"),
                    "longitude": result.get("lon"),
                    "country": address.get("country"),
                    "admin1": address.get("state"),
                })
            if len(candidates) > 1:
                top_name = str(candidates[0].get("name", "")).casefold()
                second_name = str(candidates[1].get("name", "")).casefold()
                if top_name and top_name == second_name:
                    raise WeatherIntegrationError("ambiguous_location")
            top = candidates[0]
            latitude = _number(top.get("latitude"))
            longitude = _number(top.get("longitude"))
            place_name = top.get("name")
            if not isinstance(place_name, str) or not place_name.strip():
                place_name = attempt
            parts = [place_name]
            if top.get("admin1") and top["admin1"] != place_name:
                parts.append(top["admin1"])
            if top.get("country"):
                parts.append(top["country"])
            return {
                "latitude": latitude,
                "longitude": longitude,
                "location": ", ".join(parts),
                "name": place_name,
            }

        candidates = [place for place in results if isinstance(place, dict)]
        india_text = "india" in attempt.casefold()
        if india_text:
            india_candidates = [
                place for place in candidates
                if str(place.get("country_code", "")).upper() == "IN"
            ]
            if india_candidates:
                candidates = india_candidates
        if not candidates:
            continue

        top = candidates[0]
        if len(candidates) > 1:
            top_name = str(top.get("name", "")).casefold()
            second_name = str(candidates[1].get("name", "")).casefold()
            top_admin = str(top.get("admin1", "")).casefold()
            second_admin = str(candidates[1].get("admin1", "")).casefold()
            if top_name == second_name and top_admin == second_admin:
                raise WeatherIntegrationError("ambiguous_location")

        latitude = _number(top.get("latitude"))
        longitude = _number(top.get("longitude"))
        place_name = top.get("name")
        if not isinstance(place_name, str) or not place_name.strip():
            raise WeatherIntegrationError("invalid_provider_response")
        country = top.get("country")
        admin1 = top.get("admin1")
        location_parts = [place_name]
        if admin1 and admin1 != place_name:
            location_parts.append(admin1)
        if country:
            location_parts.append(country)
        return {
            "latitude": latitude,
            "longitude": longitude,
            "location": ", ".join(location_parts),
            "name": place_name,
        }

    raise WeatherIntegrationError("location_not_found")


def _fetch_weather_report(location, latitude=None, longitude=None, resolved_location=None):
    if latitude is None or longitude is None:
        place = resolve_location(location)
        latitude = place["latitude"]
        longitude = place["longitude"]
        resolved_location = place["location"]
    if not resolved_location:
        resolved_location = location
    forecast = _request_json(
        FORECAST_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,"
                "precipitation,rain,weather_code,wind_speed_10m,"
                "wind_direction_10m,surface_pressure,cloud_cover,is_day"
            ),
            "daily": (
                "weather_code,precipitation_probability_max,precipitation_sum,"
                "et0_fao_evapotranspiration,sunrise,sunset"
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
    daily_sunrise = daily.get("sunrise")
    daily_sunset = daily.get("sunset")
    arrays = (
        daily_dates,
        daily_codes,
        daily_probabilities,
        daily_precipitation,
        daily_et0,
    )
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
        sunrise = (
            daily_sunrise[index]
            if isinstance(daily_sunrise, list)
            and index < len(daily_sunrise)
            and isinstance(daily_sunrise[index], str)
            else None
        )
        sunset = (
            daily_sunset[index]
            if isinstance(daily_sunset, list)
            and index < len(daily_sunset)
            and isinstance(daily_sunset[index], str)
            else None
        )
        forecast_days.append(
            {
                "date": forecast_date,
                "condition": _condition(daily_codes[index]),
                "precipitation_probability_pct": _number(
                    daily_probabilities[index], optional=True
                ),
                "precipitation_mm": _number(daily_precipitation[index], optional=True),
                "et0_mm": _number(daily_et0[index], optional=True),
                "sunrise": sunrise,
                "sunset": sunset,
            }
        )

    weather_code = current.get("weather_code")
    return {
        "provider": "Open-Meteo",
        "location": resolved_location,
        "timezone": forecast.get("timezone"),
        "latitude": latitude,
        "longitude": longitude,
        "current": current_data,
        "forecast": forecast_days,
        "details": {
            "weather_code": weather_code,
            "icon": _weather_icon(weather_code),
            "rainfall_mm": _number(current.get("rain"), optional=True),
            "pressure_hpa": _number(current.get("surface_pressure"), optional=True),
            "cloud_cover_pct": _number(current.get("cloud_cover"), optional=True),
            "wind_direction_degrees": _number(current.get("wind_direction_10m"), optional=True),
            "sunrise": forecast_days[0]["sunrise"] if forecast_days else None,
            "sunset": forecast_days[0]["sunset"] if forecast_days else None,
            "last_updated": current.get("time"),
        },
    }


def get_weather_report(location=None, latitude=None, longitude=None, resolved_location=None):
    normalized_location = location.strip() if isinstance(location, str) else ""
    if normalized_location:
        if len(normalized_location) > 120:
            raise WeatherIntegrationError("invalid_location")
    elif latitude is None or longitude is None:
        raise WeatherIntegrationError("location_required")

    cache_key = (
        f"{float(latitude):.5f},{float(longitude):.5f}"
        if latitude is not None and longitude is not None
        else normalized_location.casefold()
    )
    now = time.monotonic()
    with _cache_lock:
        cached = _weather_cache.get(cache_key)
        if cached and now - cached[0] < CACHE_SECONDS:
            return cached[1]

    try:
        report = _fetch_weather_report(
            normalized_location,
            latitude=latitude,
            longitude=longitude,
            resolved_location=resolved_location,
        )
        with _cache_lock:
            _weather_cache[cache_key] = (time.monotonic(), report)
        return report
    except WeatherIntegrationError:
        with _cache_lock:
            stale = _weather_cache.get(cache_key)
        if stale:
            return stale[1]
        raise


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
