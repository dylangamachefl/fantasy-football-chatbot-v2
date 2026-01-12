# 🏈 Fantasy Football Chatbot - Backend

The FastAPI backend service that powers the Fantasy Football chatbot agent.

## Architecture

The backend uses a **5-Node LangGraph StateGraph** to process requests:

1. **Query Enhancer:** Rewrites user input to resolve pronouns and request narrative details
2. **Table Router:** Selects tables using Python-based "Owner Detection" and LLM reasoning
3. **Schema Builder:** Retrieves specific table/column context
4. **SQL Agent:** A self-correcting ReAct subgraph that generates and executes SQL
5. **Responder:** Synthesizes raw database tuples into natural, story-driven answers

**Note:** Actual SQL execution is offloaded to a separate **Sidecar Service** running on port 8081 for security and isolation.

## Project Structure

```
backend/
├── src/
│   ├── api/              # FastAPI application
│   │   ├── main.py       # API endpoints
│   │   └── models.py     # Pydantic models
│   ├── agent/            # LangGraph agent logic
│   │   ├── workflow.py   # Main graph orchestrator
│   │   ├── state.py      # State definitions
│   │   └── sql_agent.py  # SQL agent & utilities
│   ├── sidecar/          # SQL Execution Service
│   │   └── main.py       # Sidecar entrypoint
│   └── config/           # Configuration
├── data/                 # Data files (DB, CSVs)
├── requirements.txt      # Dependencies
└── Dockerfile            # Container configuration
```

## Setup

**1. Install Dependencies**

```bash
cd backend
pip install -r requirements.txt
```

**2. Environment Variables**

Ensure `.env` file exists in the project root with:
```ini
GOOGLE_API_KEY=your_google_api_key
# Langfuse Tracing
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

**3. Database**

Ensure the SQLite database is located at: `backend/data/llm_fantasy_data.db`

## Running the Backend

You must run **both** the Sidecar and the API.

**1. Start the Sidecar:**

```bash
cd backend
python -m src.sidecar.main
```
(Runs on port 8081)

**2. Start the API:**

```bash
cd backend
python -m uvicorn src.api.main:app --reload --port 8000
```

The API will be available at:
- **Base URL:** http://localhost:8000
- **Health check:** http://localhost:8000/health
- **API docs:** http://localhost:8000/docs

## API Endpoints

### `GET /health`
Health check endpoint.

**Response:**
```json
{"status": "ok"}
```

### `POST /chat`
Process a user query through the LangGraph agent.

**Request:**
```json
{
  "query": "Who won the championship in 2020?",
  "thread_id": "optional-thread-id"
}
```

**Response:**
```json
{
  "answer": "Jack won the championship in 2020...",
  "thread_id": "thread-id-for-conversation",
  "sql_debug": "Hidden in Prod"
}
```

## Key Files

- **`src/api/main.py`**: FastAPI application and endpoints
- **`src/agent/workflow.py`**: The main LangGraph orchestrator
- **`src/agent/sql_agent.py`**: SQL agent subgraph and database utilities
- **`src/sidecar/main.py`**: The SQL execution service

## Development

The backend uses:
- **FastAPI** for the REST API
- **LangGraph** for the agent workflow
- **LangChain** for LLM interactions
- **Google Gemini** as the LLM
- **SQLite** for the fantasy football database
