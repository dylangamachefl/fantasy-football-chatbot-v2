# api.py
import uuid
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage

# Import your existing graph
from graph_builder import workflow

# Setup
app = FastAPI(title="Fantasy Football Agent API")

# Initialize Memory (Note: In-memory persistence wipes on restart.
# For production, use PostgresCheckpointer)
memory = MemorySaver()
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

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest):
    try:
        # 1. Handle Thread ID
        thread_id = payload.thread_id or str(uuid.uuid4())

        # 2. Config for Persistence
        config = {"configurable": {"thread_id": thread_id}}

        # 3. Prepare Input
        input_message = HumanMessage(content=payload.query)

        # 4. Run Graph (Async for performance)
        # We use ainvoke so the server doesn't block while waiting for Gemini
        final_state = await agent_app.ainvoke(
            {"messages": [input_message], "input": payload.query},
            config=config
        )

        # 5. Extract Output
        last_message = final_state["messages"][-1].content

        # (Optional) Extract SQL for debugging if available in state
        # This depends on how you store it in AgentState
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
