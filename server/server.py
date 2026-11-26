from datetime import date

from mcp.server.mcpserver import MCPServer
import httpx

# 1. Server nesnesi
mcp = MCPServer("climate-mcp")

# 2. Fonksiyonu tool'a çeviren dekoratör
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
async def get_forecast(latitude: float, longitude: float, days: int = 7) -> dict:
    """Get the daily weather forecast for a location, starting today and up to 16 days ahead.
    Use this for today and any future date. For yesterday or any earlier date, use
    get_historical instead. Requires coordinates; if you only have a place name,
    call geocode_city first.

    Args:
        latitude: Latitude in decimal degrees, -90 to 90
        longitude: Longitude in decimal degrees, -180 to 180
        days: Number of forecast days starting today, 1 to 16
    """

    if days < 1 or days > 16:
        return {"error": "Invalid number of forecast days. Please specify a value between 1 and 16."}

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "forecast_days": days,
        "timezone": "auto",
        "daily": ",".join(["temperature_2m_max", "temperature_2m_min", "precipitation_sum"]),
    }

    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=10)
    data = response.json()

    if response.status_code != 200:
        return {"error": data.get("reason", "Unknown error from Open-Meteo API.")}

    daily = data["daily"]
    rows = []
    for i, date in enumerate(daily["time"]):
        rows.append({
            "date": date,
            "temperature_max_c": daily["temperature_2m_max"][i],
            "temperature_min_c": daily["temperature_2m_min"][i],
            "precipitation_mm": daily["precipitation_sum"][i]
        })

    return {
        "location": {"latitude": data["latitude"], "longitude": data["longitude"]},
        "days": rows,
    }
# 3. Server'ı başlatmak
if __name__ == "__main__":
    mcp.run()