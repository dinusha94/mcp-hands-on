from mcp.server.fastmcp import FastMCP
import httpx
import asyncio
import os
from mcp import StdioServerParameters
from dotenv import load_dotenv

load_dotenv()
WEATHER_API_KEY = os.environ["WEATHER_API_KEY"] 

mcp = FastMCP("MCP-DEMO")

@mcp.tool()
def calculate_bmi(weight_kg: float, height_m: float) -> float:
    """Calculate BMI given weight in kg and height in meters"""
    return weight_kg / (height_m ** 2)

@mcp.tool()
async def fetch_weather(city: str) -> str:
    """Fetch current weather for a city using WeatherAPI."""
   
    url = f"http://api.weatherapi.com/v1/current.json?key={WEATHER_API_KEY}&q={city}"

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

  