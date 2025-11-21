"""FastAPI application for the Fantasy Football Agent."""

import uuid
import json
import csv
import logging
import os
import aiosqlite
from typing import AsyncGenerator
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import the workflow from the agent package
try:
    from src.agent.workflow import workflow
except ImportError:
    from ..agent.workflow import workflow

# Import models
from .models import ChatRequest, ChatResponse, FeedbackRequest

# Initialize Persistence (SQLite)
DB_PATH = "data/chat_history.db"

# Ensure data directory exists
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# Globals for lifecycle management
agent_app = None
db_connection = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent_app, db_connection
    # Startup
    db_connection = await aiosqlite.connect(DB_PATH)
    checkpointer = AsyncSqliteSaver(db_connection)
    await checkpointer.setup()
    agent_app = workflow.compile(checkpointer=checkpointer)
    yield
    # Shutdown
    if db_connection:
        await db_connection.close()

# Setup
app = FastAPI(title="Fantasy Football Agent API", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all for dev; restrict in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Feedback File
FEEDBACK_FILE = "data/feedback.csv"

# --- Endpoints ---

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/feedback")
async def feedback_endpoint(payload: FeedbackRequest):
    """
    Endpoint to save user feedback.
    """
    try:
        # Append to CSV
        with open(FEEDBACK_FILE, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().isoformat(),
                payload.thread_id,
                payload.user_input,
                payload.assistant_response,
                payload.feedback_type
            ])
        return {"status": "success", "message": "Feedback recorded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def stream_generator(query: str, thread_id: str) -> AsyncGenerator[str, None]:
    """
    Generates SSE events for the chat stream.
    Events:
    - token: A chunk of the final answer.
    - sql: The SQL query executed.
    - data: The structured data returned by the SQL query (JSON).
    - error: Any error message.
    - done: End of stream.
    """
    config = {"configurable": {"thread_id": thread_id}}
    input_message = HumanMessage(content=query)

    try:
        # Use astream_events to get granular updates
        async for event in agent_app.astream_events(
            {"messages": [input_message], "input": query},
            config=config,
            version="v1"
        ):
            kind = event["event"]

            # 1. Capture SQL Query (Input to Tool)
            if kind == "on_tool_start" and event["name"] == "sql_db_query":
                data = event["data"].get("input")
                # It could be a dict or string depending on how it's called
                sql = data.get("query") if isinstance(data, dict) else data
                if sql:
                    yield f"event: sql\ndata: {json.dumps(sql)}\n\n"

            # 2. Capture SQL Result (Output from Tool)
            elif kind == "on_tool_end" and event["name"] == "sql_db_query":
                # The output is the JSON string we created in sql_agent.py
                output = event["data"].get("output")
                if output:
                    # It's already a JSON string, so we can pass it through.
                    # But we should double-check it's valid JSON or just a string.
                    # If it starts with Error, it might be a plain string.
                    # We wrap it in a JSON object for the event data.
                    yield f"event: data\ndata: {output}\n\n"

            # 3. Capture Final Answer Tokens (Streaming from Responder)
            elif kind == "on_chat_model_stream":
                # Filter for the 'responder' node.
                # Note: metadata keys might vary, usually 'langgraph_node' or 'tags'
                if event.get("metadata", {}).get("langgraph_node") == "responder":
                    chunk = event["data"]["chunk"]
                    if chunk.content:
                        # Dump to ensure newlines are escaped
                        yield f"event: token\ndata: {json.dumps(chunk.content)}\n\n"

        # End of stream
        yield "event: done\ndata: [DONE]\n\n"

    except Exception as e:
        yield f"event: error\ndata: {json.dumps(str(e))}\n\n"


@app.post("/chat")
async def chat_endpoint(payload: ChatRequest):
    """
    Chat endpoint that processes user queries through the LangGraph agent.
    Returns a StreamingResponse.
    """
    thread_id = payload.thread_id or str(uuid.uuid4())

    # Return the thread_id in a header or just rely on the client knowing it?
    # Standard SSE doesn't handle headers well in the middle.
    # We will send the thread_id as the first event or just rely on the client preserving it.
    # Let's send a 'meta' event first.

    async def wrapper():
        yield f"event: meta\ndata: {json.dumps({'thread_id': thread_id})}\n\n"
        async for chunk in stream_generator(payload.query, thread_id):
            yield chunk

    return StreamingResponse(wrapper(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
