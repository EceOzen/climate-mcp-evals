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

# 3. Server'ı başlatmak
if __name__ == "__main__":
    mcp.run()