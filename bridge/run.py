import sys
import json
import anyio
from mcp import Client, StdioServerParameters
import os
from datetime import date

import cohere
from dotenv import load_dotenv

load_dotenv()  # reads COHERE_API_KEY from .env
co = cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"])
MODEL = "command-a-plus-05-2026"
MAX_TURNS = 5  # safety limit against endless tool loops

server = StdioServerParameters(
    command=sys.executable,          # same Python that runs this script (the conda env)
    args=["server/server.py"],
)

def to_cohere_tools(mcp_tools) -> list[dict]:
    """Convert MCP tool definitions to Cohere's tool format."""
    cohere_tools = []
    for tool in mcp_tools:
        cohere_tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        })

    return cohere_tools

async def run_tool(client, tool_call) -> dict:
    """Execute one Cohere tool call on the MCP server and return its result."""
    args = json.loads(tool_call.function.arguments)
    result = await client.call_tool(tool_call.function.name, args)
    if result.is_error:
        return {"error": f"Tool {tool_call.function.name} failed"}
    if result.structured_content is not None:
        return result.structured_content
    # Fall back to the text blocks when the server sends no structured content
    text = "".join(block.text for block in result.content if hasattr(block, "text"))
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"result": text}


async def main() -> None:
    async with Client(server) as client:
        result = await client.list_tools()
        cohere_tools = to_cohere_tools(result.tools)

        messages = [
            {"role": "system", "content": f"Today is {date.today().isoformat()}."},
            {"role": "user", "content": "Will it rain in Ankara tomorrow?"},
        ]

        for turn in range(MAX_TURNS):
            response = co.chat(model=MODEL, messages=messages, tools=cohere_tools)

            if not response.message.tool_calls:
                answer = "".join(item.text for item in response.message.content if item.type == "text")
                print("\nAnswer:", answer)
                return

            messages.append(response.message)
            for tc in response.message.tool_calls:
                print(f"[turn {turn}] {tc.function.name} {tc.function.arguments}")
                tool_result = await run_tool(client, tc)
                print("  result:", tool_result)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": [{"type": "document", "document": {"data": json.dumps(tool_result)}}],
                })

        print("Stopped: reached MAX_TURNS without a final answer.")
        
if __name__ == "__main__":
    anyio.run(main)