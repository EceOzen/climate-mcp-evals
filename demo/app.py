"""Streamlit chat demo: ask the agent a question and watch every tool call it makes."""
import json
import sys
from datetime import date
from pathlib import Path

import anyio
import streamlit as st
from mcp import Client

# Make the repo root importable when Streamlit runs this file from demo/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge.run import MAX_TURNS, MODEL, co, run_tool, server, to_cohere_tools  # noqa: E402

EXAMPLES = [
    "Will it rain in Ankara tomorrow?",
    "How much did it rain in Istanbul in the first week of November 2026?",
    "Which will be warmer tomorrow, Izmir or Trabzon?",
]


async def ask(question: str, history: list[dict], on_step) -> str:
    """Run the tool-use loop for one question, reporting each tool call to on_step."""
    async with Client(server) as client:
        tools = to_cohere_tools((await client.list_tools()).tools)
        messages = [
            {"role": "system", "content": f"Today is {date.today().isoformat()}."},
            *history,
            {"role": "user", "content": question},
        ]

        for _ in range(MAX_TURNS):
            response = co.chat(model=MODEL, messages=messages, tools=tools)
            if not response.message.tool_calls:
                return "".join(
                    item.text for item in response.message.content if item.type == "text"
                )

            messages.append(response.message)
            for tc in response.message.tool_calls:
                result = await run_tool(client, tc)
                on_step(tc.function.name, json.loads(tc.function.arguments), result)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": [{"type": "document", "document": {"data": json.dumps(result)}}],
                })

        return "Stopped: the model kept calling tools without giving an answer."


st.set_page_config(page_title="Climate data agent", page_icon="🌦️")
st.title("Climate data agent")
st.caption(
    f"{MODEL} with an MCP server over Open-Meteo forecasts and ERA5 history. "
    "Each tool call is shown as it happens."
)

with st.sidebar:
    st.subheader("Try asking")
    for example in EXAMPLES:
        st.markdown(f"- {example}")
    if st.button("Clear conversation"):
        st.session_state.history = []
        st.rerun()

if "history" not in st.session_state:
    st.session_state.history = []

# Replay the conversation so far (text turns only; tool calls are not kept)
for message in st.session_state.history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if question := st.chat_input("Ask about the weather or climate of a place"):
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        status = st.status("Working…", expanded=True)

        def on_step(name: str, args: dict, result: dict) -> None:
            status.markdown(f"**{name}** `{json.dumps(args, ensure_ascii=False)}`")
            status.json(result, expanded=False)

        answer = anyio.run(ask, question, st.session_state.history, on_step)
        status.update(label="Tool calls", state="complete", expanded=False)
        st.markdown(answer)

    st.session_state.history += [
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer},
    ]