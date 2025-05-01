from mcp.server.fastmcp import FastMCP
import httpx
import asyncio
import os
from mcp import ClientSession, StdioServerParameters, types
import base64

mcp = FastMCP("MCP-DEMO")

@mcp.tool()
def calculate_bmi(weight_kg: float, height_m: float) -> float:
    """Calculate BMI given weight in kg and height in meters"""
    return weight_kg / (height_m ** 2)

@mcp.tool()
async def fetch_weather(latitude: float, longitude: float) -> str:
    """Fetch current weather for a location using latitude and longitude"""
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={latitude}&longitude={longitude}&current_weather=true&"
        f"hourly=temperature_2m,relative_humidity_2m,wind_speed_10m"
    )
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.text


@mcp.resource("file:///logs-resource")
def read_log_file():
    """Read and return the contents of a log file."""
    try:
        with open('./logs/app.log', 'r', encoding='utf-8') as f:
            content = f.read()
        return content

    except Exception as e:
        return {
            "error": f"Error reading file: {e}"
        }
        
if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Start background async tasks (if needed)
    loop.run_until_complete(asyncio.sleep(0))  

    # Now run FastMCP (blocking)
    mcp.run()

  