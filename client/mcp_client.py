from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
import logging
import json
import os
import asyncio
from dotenv import load_dotenv
import openai

load_dotenv()
logging.basicConfig(level=logging.INFO)

server_params = StdioServerParameters(
    command="python",
    args=["server/example_server.py"],
)

OPENAI_API_VERSION = os.environ["OPENAI_API_VERSION"] 
AZURE_OPENAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
AZURE_OPENAI_API_KEY = os.environ["AZURE_OPENAI_API_KEY"]

openai_client = openai.AsyncAzureOpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    api_version=OPENAI_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT
)

LOCAL_FUNCTIONS = {
    "calculate_bmi": {
        "keywords": ["bmi", "body mass index"],
        "description": "Calculates Body Mass Index (BMI) using weight (kg) and height (m).",
        "tool_name": "calculate_bmi",
        "prompts": ["Enter weight in kg: ", "Enter height in meters: "],
        "format_args": lambda w, h: {"weight_kg": float(w), "height_m": float(h)},
        "response_format": lambda res: f"Your BMI is: {res}",
    },
    "get_weather": {
        "keywords": ["weather", "forecast"],
        "description": "Fetches current weather for a given latitude and longitude.",
        "tool_name": "fetch_weather",
        "prompts": ["Enter latitude: ", "Enter longitude: "],
        "format_args": lambda lat, lon: {"latitude": float(lat), "longitude": float(lon)},
        "response_format": lambda res: (
            f"{json.loads(res).get('current_weather', {}).get('temperature', 'N/A')}\u00b0C"
            if res and isinstance(res, str) and res.strip() else "Error: No response from API"
        ),
    },
    "read_logs": {
        "keywords": ["logs"],
        "description": "Reads and returns the most recent application logs.",
        "resource_uri": "file:///logs-resource",
        "prompts": [],
        "format_args": lambda: {},
        "response_format": lambda res: res,
    },
}

# maintain a common chat history
conversation_history = [{"role": "system", "content": "You are a helpful assistant."}]

# Create a function to generate the tool selection prompt
def build_tool_selection_prompt(user_input):
    tool_descriptions = "\n".join(
        f"- {name}: {info['description']}" for name, info in LOCAL_FUNCTIONS.items()
    )
    return f"""
                You are a routing assistant. Based on the user message, choose the most appropriate tool from the list below.

                Available tools:
                {tool_descriptions}

                User message: "{user_input}"

                Return only the tool name (e.g., "calculate_bmi") or "none" if no tool is relevant.
                """

async def handle_openai_sampling(message: types.CreateMessageRequestParams) -> types.CreateMessageResult:
    try:
        user_content = next((c.text for m in message.messages for c in getattr(m, "content", []) if c.type == "text"), "Hello, please assist me.")
        conversation_history.append({"role": "user", "content": user_content})

        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini", messages=conversation_history
        )

        ai_text = response.choices[0].message.content
        conversation_history.append({"role": "assistant", "content": ai_text})
        
        return types.CreateMessageResult(role="assistant", content=types.TextContent(type="text", text=ai_text), model="gpt-4o-mini", stopReason="endTurn")
    except Exception as e:
        logging.error(f"OpenAI API error: {e}")
        return types.CreateMessageResult(role="assistant", content=types.TextContent(type="text", text=f"Error: {e}"), model="gpt-4o-mini", stopReason="error")

async def detect_and_handle_local_function(user_input, session):
    user_input_lower = user_input.lower()
    
    prompt = build_tool_selection_prompt(user_input)
    

    # Use the LLM to choose the most appropriate tool
    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",  
        messages=[
            {"role": "system", "content": "You are a tool selector that only returns tool names."},
            {"role": "user", "content": prompt}
        ],
        temperature=0,
    )

    selected_tool = response.choices[0].message.content.strip().lower()

    
    for func_name, func_info in LOCAL_FUNCTIONS.items():
        # if any(keyword in user_input_lower for keyword in func_info["keywords"]):
        if func_name == selected_tool:
            print(f"\n[USING FUNCTION OR RESOURCE: {func_name}]")
            try:
                if "tool_name" in func_info:
                    args = func_info["format_args"](*[input(p) for p in func_info["prompts"]])
                    tool_result = await session.call_tool(func_info["tool_name"], arguments=args) # calls an mcp tool
                    content_list = tool_result.content
                    if content_list:
                        result = content_list[0].text
                        formatted_response = func_info["response_format"](result)
                        print(f"\nAssistant: {formatted_response}")
                        conversation_history.extend([
                            {"role": "user", "content": user_input},
                            {"role": "assistant", "content": formatted_response}
                        ])
                        return True
                elif "resource_uri" in func_info:
                    resource_result = await session.read_resource(func_info["resource_uri"]) # reads from mcp resource
                    content = resource_result.contents[0].text
                    if isinstance(content, str):
                        print(f"\nAssistant: {content}")
                        conversation_history.extend([
                            {"role": "user", "content": user_input}, 
                            {"role": "assistant", "content": content}
                        ])
                        
                        return True
            except Exception as e:
                logging.error(f"Error calling {func_name}: {e}")
                print(f"\nAssistant: Error processing request.")
                return True
    return False

async def run():
    print("\n===== MCP CLIENT =====\n")
    
    async with stdio_client(server_params) as (read, write): # start the mcp server
        
        async with ClientSession(read, write, sampling_callback=handle_openai_sampling) as session:
            
            # initialize the client session
            await session.initialize()

            print(f"Available tools: {[tool.name for tool in (await session.list_tools()).tools]}")
            print(f"Available resources: {[resource.name for resource in (await session.list_resources()).resources]}")

            while True:
                user_input = input("\nYou: ").strip()
                if user_input.lower() == "exit":
                    print("Exiting...")
                    break
                
                # based on the user input check if we need to use a local tools, if not use LLM
                if not await detect_and_handle_local_function(user_input, session):
                    print("\n[USING OpenAI]")
                    conversation_history.append({"role": "user", "content": user_input})
                    response = await openai_client.chat.completions.create(
                        model="gpt-4o-mini", messages=conversation_history
                    )
                    assistant_response = response.choices[0].message.content
                    print(f"\nAssistant: {assistant_response}")
                    conversation_history.append({"role": "assistant", "content": assistant_response})

if __name__ == "__main__":
    asyncio.run(run())
