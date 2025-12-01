# 🏈 Fantasy Football Chatbot

A conversational AI agent powered by **LangGraph**, **LangChain**, and **Google Gemini** that performs advanced SQL analysis on a fantasy football SQLite database.

## ⚡ Architecture

The agent uses a **5-Node StateGraph** to process requests:
1.  **Query Enhancer:** Rewrites user input to resolve pronouns ("he" → "Dylan") and request narrative details (scores, opponents).
2.  **Table Router:** Selects tables using Python-based "Owner Detection" and LLM reasoning.
3.  **Schema Builder:** Retrieves specific table/column context.
4.  **SQL Agent:** A self-correcting ReAct subgraph that generates and executes SQL.
5.  **Responder:** Synthesizes raw database tuples into natural, story-driven answers.

## 📂 Project Structure

```
fantasy-football-chatbot-v2/
├── backend/              # FastAPI backend service
│   ├── src/
│   │   ├── api/         # API endpoints and models
│   │   └── agent/       # LangGraph agent logic
│   └── requirements.txt
├── frontend/            # Streamlit frontend
│   ├── app.py
│   └── requirements.txt
├── data/                # Shared data files
│   └── llm_fantasy_data.db
├── evals/               # Evaluation scripts
└── docker-compose.yml   # Multi-service orchestration
```

## 🛠 Setup

**1. Install Dependencies**

Requires Python 3.10+.

For backend:
```bash
cd backend
pip install -r requirements.txt
```

For frontend:
```bash
cd frontend
pip install -r requirements.txt
```

**2. Environment Variables**

Create a `.env` file in the root directory:
```ini
GOOGLE_API_KEY=your_google_api_key
# Langfuse Tracing
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

**3. Database**

Ensure your SQLite database is located at: `data/llm_fantasy_data.db`

## 🚀 Usage

### Option 1: Run Services Separately

**Start the Backend API:**
```bash
cd backend
python -m uvicorn src.api.main:app --reload --port 8000
```

**Start the Frontend (in a new terminal):**
```bash
cd frontend
streamlit run app.py
```

### Option 2: Use Docker Compose

```bash
docker-compose up
```

This will start both services together:
- Backend API: http://localhost:8000
- Frontend UI: http://localhost:8501

## 🧪 Run Evaluations

Run the conversational test suite:
```bash
cd evals
python run_conversation_evals.py
```

## 📂 Key Files

*   **`backend/src/agent/workflow.py`**: The Orchestrator. Contains the **Query Enhancer**, **Router**, and **Responder** nodes.
*   **`backend/src/agent/sql_agent.py`**: The Specialist. Contains the **SQL Agent Subgraph**, System Prompts, and Table Definitions.
*   **`frontend/app.py`**: Streamlit frontend with Session State and conversation persistence.
*   **`backend/src/api/main.py`**: FastAPI application with `/chat` endpoint.

## 📖 Documentation

- [Backend README](backend/README.md) - Backend architecture and API documentation
- [Frontend README](frontend/README.md) - Frontend setup and usage