from datetime import date

from mcp.server.mcpserver import MCPServer
import httpx
from typing import Literal

Variable = Literal["temperature_max", "temperature_min", "precipitation", "wind_speed_max"]

OPEN_METEO_NAMES = {
    "temperature_max": "temperature_2m_max",
    "temperature_min": "temperature_2m_min",
    "precipitation": "precipitation_sum",
    "wind_speed_max": "wind_speed_10m_max",
}

OUTPUT_NAMES = {
    "temperature_max": "temperature_max_c",
    "temperature_min": "temperature_min_c",
    "precipitation": "precipitation_mm",
    "wind_speed_max": "wind_speed_max_kmh",
}

def _reshape_daily(data: dict, variables: list[str]) -> dict:
    daily = data["daily"]
    rows = []
    for i, day in enumerate(daily["time"]):
        row = {"date": day}
        for v in variables:
            row[OUTPUT_NAMES[v]] = daily[OPEN_METEO_NAMES[v]][i]
        rows.append(row)
    return {
        "location": {"latitude": data["latitude"], "longitude": data["longitude"]},
        "days": rows,
    }

mcp = MCPServer("climate-mcp")

@mcp.tool()
async def geocode_city(name: str, country_code: str | None = None) -> dict:
    """Geocode a city.

    Args:
        name: Name of the city
        country_code: ISO country code
    """

    async with httpx.AsyncClient() as client:
        url = "https://geocoding-api.open-meteo.com/v1/search"
        params = {"name": name, "count": 1}
        if country_code:
            params["countryCode"] = country_code.upper()

        response = await client.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])

        if not results:
             where = f" in country '{country_code}'" if country_code else ""
             return {"error": f"No place found for '{name}'{where}."}

        location = results[0]

        return {
            "latitude": location.get("latitude"),
            "longitude": location.get("longitude"),
            "name": location.get("name"),
            "country": location.get("country"),
            "country_code": location.get("country_code"),
        }
@mcp.tool()
async def get_forecast(latitude: float, longitude: float, days: int = 7, variables: list[Variable]| None = None ) -> dict:
    """Get the daily weather forecast for a location, starting today and up to 16 days ahead.
    Use this for today and any future date. For yesterday or any earlier date, use
    get_historical instead. Requires coordinates; if you only have a place name,
    call geocode_city first.

    Args:
        latitude: Latitude in decimal degrees, -90 to 90
        longitude: Longitude in decimal degrees, -180 to 180
        days: Number of forecast days starting today, 1 to 16
    """

    if not variables:
        variables = list(OPEN_METEO_NAMES)

    if days < 1 or days > 16:
        return {"error": "Invalid number of forecast days. Please specify a value between 1 and 16."}

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "forecast_days": days,
        "timezone": "auto",
        "daily": ",".join(OPEN_METEO_NAMES[v] for v in variables),
    }

    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=10)
    data = response.json()

    if response.status_code != 200:
        return {"error": data.get("reason", "Unknown error from Open-Meteo API.")}

    return _reshape_daily(data, variables)
@mcp.tool()
async def get_historical(latitude: float, longitude: float, start_date: str, end_date: str, variables: list[Variable] | None = None) -> dict:
    """Get the daily historical weather data for a location between two dates.
    Use this for yesterday or any earlier date. For today or any future date, use
    get_forecast instead. Requires coordinates; if you only have a place name,
    call geocode_city first.

    Args:
        latitude: Latitude in decimal degrees, -90 to 90
        longitude: Longitude in decimal degrees, -180 to 180
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        variables: Which daily variables to return. Defaults to all.
    """
    if not variables:
        variables = list(OPEN_METEO_NAMES)

    # Validate date format and range
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError:
        return {"error": "Invalid date format. Please use YYYY-MM-DD."}

    if start > end:
        return {"error": "Start date must be before or equal to end date."}

    if end > date.today():
        return {"error": "End date must be before today. For today or future dates, use get_forecast."}

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
        "timezone": "auto",
        "daily": ",".join(OPEN_METEO_NAMES[v] for v in variables)
    }

    async with httpx.AsyncClient() as client:
        response = await client.get("https://archive-api.open-meteo.com/v1/archive", params=params, timeout=10)
    data = response.json()

    if response.status_code != 200:
        return {"error": data.get("reason", "Unknown error from Open-Meteo API.")}

    return _reshape_daily(data, variables)


if __name__ == "__main__":
    mcp.run()