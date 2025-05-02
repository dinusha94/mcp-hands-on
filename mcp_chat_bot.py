import asyncio
import logging
import os
import openai
from typing import List, Dict
import aiofiles
from dotenv import load_dotenv
import json
import httpx

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

load_dotenv()

OPENAI_API_VERSION = os.environ["OPENAI_API_VERSION"] 
AZURE_OPENAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
AZURE_OPENAI_API_KEY = os.environ["AZURE_OPENAI_API_KEY"]
WEATHER_API_KEY = os.environ["WEATHER_API_KEY"] 



 # Initialize your LLM client (assuming a basic setup here)
llm_client = openai.AsyncAzureOpenAI(
            api_key=AZURE_OPENAI_API_KEY,
            api_version=OPENAI_API_VERSION,
            azure_endpoint=AZURE_OPENAI_ENDPOINT
        )


# Create set of example tools
async def calculate_bmi(weight_kg: float, height_m: float) -> float:
    """Calculate BMI given weight in kg and height in meters."""
    return weight_kg / (height_m ** 2)

async def fetch_weather(city: str) -> str:
    """Fetch current weather for a city using WeatherAPI."""
   
    url = f"http://api.weatherapi.com/v1/current.json?key={WEATHER_API_KEY}&q={city}"

    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.text


async def read_log_file():
    """Read and return the contents of a log file asynchronously."""
    try:
        async with aiofiles.open('./logs/app.log', 'r', encoding='utf-8') as f:
            content = await f.read()
        return content
    except Exception as e:
        return {"error": f"Error reading file: {e}"}


# Class that represents a tool that can be executed.
class Tool:
    
    def __init__(self, name: str, description: str, func: callable):
        self.name = name
        self.description = description
        self.func = func

    async def execute(self, arguments: Dict) -> str:
        try:
            result = await self.func(**arguments)
            return result
        except Exception as e:
            logging.error(f"Error executing tool {self.name}: {e}")
            return {"error": str(e)}

# Class that represents a server that can execute tools.
class Server:
  
    def __init__(self, name: str, tools: List[Tool]):
        self.name = name
        self.tools = tools

    async def initialize(self) -> None:
        """Initialize the server (dummy initialization)."""
        logging.info(f"Initializing server {self.name}")
        await asyncio.sleep(1)

    async def list_tools(self) -> List[Tool]:
        """List all tools available on this server."""
        return self.tools

    async def execute_tool(self, tool_name: str, arguments: Dict) -> str:
        """Execute the requested tool with arguments."""
        for tool in self.tools:
            if tool.name == tool_name:
                return await tool.execute(arguments)
        return {"error": f"Tool {tool_name} not found on server {self.name}"}
    
    async def cleanup(self) -> None:
        """Clean up server resources."""
        logging.info(f"Cleaning up server {self.name}")
        await asyncio.sleep(1)


# Orchestrates the interaction between user, LLM, and tools.
class ChatSession:

    def __init__(self, servers: List[Server]) -> None:
        self.servers: List[Server] = servers

    async def cleanup_servers(self) -> None:
        """Clean up all servers properly."""
        cleanup_tasks = [
            asyncio.create_task(server.cleanup()) for server in self.servers
        ]
        if cleanup_tasks:
            try:
                await asyncio.gather(*cleanup_tasks, return_exceptions=True)
            except Exception as e:
                logging.warning(f"Warning during final cleanup: {e}")

    async def process_llm_response(self, llm_response: str) -> str:
        """Process the LLM response and execute tools if needed.

        Args:
            llm_response: The response from the LLM.

        Returns:
            The result of tool execution or the original response.
        """

        try:
            # Await the LLMClient response to get the actual string, not the coroutine
            if isinstance(llm_response, str):
                tool_call = json.loads(llm_response)
            else:
                # Await the response if it is not already a string
                llm_response = await llm_response
                tool_call = json.loads(llm_response)

            if "tool" in tool_call and "arguments" in tool_call:
                logging.info(f"Executing tool: {tool_call['tool']}")
                logging.info(f"With arguments: {tool_call['arguments']}")

                for server in self.servers:
                    tools = await server.list_tools()
                    if any(tool.name == tool_call["tool"] for tool in tools):
                        try:
                            result = await server.execute_tool(
                                tool_call["tool"], tool_call["arguments"]
                            )
                          
                            if isinstance(result, dict) and "progress" in result:
                                progress = result["progress"]
                                total = result["total"]
                                percentage = (progress / total) * 100
                                logging.info(
                                    f"Progress: {progress}/{total} "
                                    f"({percentage:.1f}%)"
                                )

                            return f"Tool execution result: {result}"
                        except Exception as e:
                            error_msg = f"Error executing tool: {str(e)}"
                            logging.error(error_msg)
                            return error_msg

                return f"No server found with tool: {tool_call['tool']}"
            return llm_response
        except json.JSONDecodeError:
            return llm_response


    async def start(self) -> None:
        """Main chat session handler."""
        try:
            for server in self.servers:
                try:
                    await server.initialize()
                except Exception as e:
                    logging.error(f"Failed to initialize server: {e}")
                    await self.cleanup_servers()
                    return

            all_tools = []
            for server in self.servers:
                tools = await server.list_tools()
                all_tools.extend(tools)

            # tools_description = "\n".join([tool.name for tool in all_tools])
            tools_description = "\n\n".join(
                [f"Tool Name: {tool.name}\nDescription: {tool.description}" for tool in all_tools]
            )

            system_message = (
                "You are a helpful assistant with access to these tools:\n\n"
                f"{tools_description}\n"
                "Choose the appropriate tool based on the user's question. "
                "If no tool is needed, reply directly.\n\n"
                "IMPORTANT: When you need to use a tool, you must ONLY respond with "
                "the exact JSON object format below, nothing else:\n"
                "{\n"
                '    "tool": "tool-name",\n'
                '    "arguments": {\n'
                '        "argument-name": "value"\n'
                "    }\n"
                "}\n\n"
                "After receiving a tool's response:\n"
                "1. Transform the raw data into a natural, conversational response\n"
                "2. Keep responses concise but informative\n"
                "3. Focus on the most relevant information\n"
                "4. Use appropriate context from the user's question\n"
                "5. Avoid simply repeating the raw data\n\n"
                "Please use only the tools that are explicitly defined above."
            )

            messages = [{"role": "system", "content": system_message}]

            while True:
                try:
                    user_input = input("You: ").strip().lower()
                    if user_input in ["quit", "exit"]:
                        logging.info("\nExiting...")
                        break

                    messages.append({"role": "user", "content": user_input})

                    # llm_response = self.llm_client.get_response(messages)
                    response = await llm_client.chat.completions.create(
                                        model="gpt-4o-mini", messages=messages
                                    )
                    llm_response = response.choices[0].message.content
                    logging.info("\nAssistant: %s", llm_response)

                    result = await self.process_llm_response(llm_response)

                    if result != llm_response:
                        messages.append({"role": "assistant", "content": llm_response})
                        messages.append({"role": "system", "content": result})

                        # final_response = self.llm_client.get_response(messages)
                        _response = await llm_client.chat.completions.create(
                                        model="gpt-4o-mini", messages=messages
                                    )
                        final_response = _response.choices[0].message.content
                        
                        logging.info("\nFinal response: %s", final_response)
                        messages.append(
                            {"role": "assistant", "content": final_response}
                        )
                    else:
                        messages.append({"role": "assistant", "content": llm_response})

                except KeyboardInterrupt:
                    logging.info("\nExiting...")
                    break

        finally:
            await self.cleanup_servers()



async def main() -> None:
    """Initialize and run the chat session."""
    # Define your tools
    tools = [
        Tool("calculate_bmi", "Calculate BMI given weight in kg and height in meters.", calculate_bmi),
        Tool("fetch_weather", "Fetch current weather for a city using WeatherAPI, argument is just the city name" , fetch_weather),
        Tool("read_log_file", "Read and return the contents of a log file asynchronously.", read_log_file)
    ]

    # Create a server with these tools
    server = Server(name="MCP-DEMO", tools=tools)  

    # Initialize and run the chat session
    chat_session = ChatSession(servers=[server])
    await chat_session.start()

if __name__ == "__main__":
    asyncio.run(main())

