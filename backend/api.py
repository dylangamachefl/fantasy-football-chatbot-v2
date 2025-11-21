# api.py
import uuid
import json
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.messages import HumanMessage, AIMessage

# Import your existing graph
from graph_builder import workflow

# Setup
app = FastAPI(title="Fantasy Football Agent API")

# Add CORS middleware to allow Streamlit frontend to make requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],  # Streamlit default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize SQLite-based persistent memory
# This will create a 'checkpoints.db' file in the current directory
memory = SqliteSaver.from_conn_string("checkpoints.db")
agent_app = workflow.compile(checkpointer=memory)

# --- Data Models ---
class ChatRequest(BaseModel):
    query: str
    thread_id: str = None # Optional: Client provides it, or we generate it

class ChatResponse(BaseModel):
    answer: str
    thread_id: str
    sql_debug: str = None

# --- Endpoints ---

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/chat/stream")
async def chat_stream_endpoint(payload: ChatRequest):
    """
    Streaming endpoint that yields Server-Sent Events (SSE) format.
    Each event contains a JSON object with type and data.
    """
    async def event_generator():
        try:
            # 1. Handle Thread ID
            thread_id = payload.thread_id or str(uuid.uuid4())
            
            # Send thread_id first
            yield f"data: {json.dumps({'type': 'thread_id', 'thread_id': thread_id})}\n\n"

            # 2. Config for Persistence
            config = {"configurable": {"thread_id": thread_id}}

            # 3. Prepare Input
            input_message = HumanMessage(content=payload.query)

            # 4. Stream events from the graph
            accumulated_content = ""
            final_state = None
            
            async for event in agent_app.astream_events(
                {"messages": [input_message], "input": payload.query},
                config=config,
                version="v2"
            ):
                kind = event["event"]
                
                # Stream LLM tokens as they're generated
                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    if hasattr(chunk, "content") and chunk.content:
                        accumulated_content += chunk.content
                        yield f"data: {json.dumps({'type': 'token', 'content': chunk.content})}\n\n"
                        await asyncio.sleep(0)  # Allow other tasks to run
                
                # When the graph completes, capture the final state
                elif kind == "on_chain_end" and event["name"] == "LangGraph":
                    final_state = event["data"]["output"]
                    # If we didn't get streaming tokens, send the full response
                    if not accumulated_content:
                        if "messages" in final_state and final_state["messages"]:
                            last_message = final_state["messages"][-1]
                            if isinstance(last_message, AIMessage):
                                content = last_message.content
                                yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
            
            # 5. Send SQL data if available
            if final_state:
                sql_result = final_state.get("sql_result")
                sql_query = final_state.get("sql_query")
                
                if sql_result and sql_query:
                    # Parse SQL result to structured data
                    try:
                        # SQL results come as string like "[(val1, val2), (val3, val4)]"
                        import ast
                        parsed_result = ast.literal_eval(sql_result)
                        
                        if isinstance(parsed_result, list) and len(parsed_result) > 0:
                            yield f"data: {json.dumps({'type': 'sql_data', 'query': sql_query, 'data': parsed_result})}\n\n"
                    except:
                        # If parsing fails, just skip visualization
                        pass
            
            # Send completion event
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            error_msg = str(e)
            yield f"data: {json.dumps({'type': 'error', 'error': error_msg})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest):
    """
    Non-streaming endpoint (kept for backward compatibility).
    """
    try:
        # 1. Handle Thread ID
        thread_id = payload.thread_id or str(uuid.uuid4())

        # 2. Config for Persistence
        config = {"configurable": {"thread_id": thread_id}}

        # 3. Prepare Input
        input_message = HumanMessage(content=payload.query)

        # 4. Run Graph (Async for performance)
        final_state = await agent_app.ainvoke(
            {"messages": [input_message], "input": payload.query},
            config=config
        )

        # 5. Extract Output
        last_message = final_state["messages"][-1].content

        # (Optional) Extract SQL for debugging if available in state
        sql_debug = "Hidden in Prod"

        return ChatResponse(
            answer=last_message,
            thread_id=thread_id,
            sql_debug=sql_debug
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
