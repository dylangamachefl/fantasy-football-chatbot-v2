# 🏈 Fantasy Football Chatbot

A conversational AI agent powered by **LangGraph**, **LangChain**, and **Google Gemini** that performs advanced SQL analysis on a fantasy football SQLite database.

## ⚡ Architecture (The Flow)
The agent uses a **5-Node StateGraph** to process requests:
1.  **Query Enhancer:** Rewrites user input to resolve pronouns ("he" $\to$ "Dylan") and request narrative details (scores, opponents).
2.  **Table Router:** Selects tables using Python-based "Owner Detection" and LLM reasoning.
3.  **Schema Builder:** Retrieves specific table/column context.
4.  **SQL Agent:** A self-correcting ReAct subgraph that generates and executes SQL.
5.  **Responder:** Synthesizes raw database tuples into natural, story-driven answers.

## 🛠 Setup

**1. Install Dependencies**
Requires Python 3.10+.
```bash
pip install -r requirements.txt
```

**2. Environment Variables**
Create a `.env` file in the root directory:
```ini
GOOGLE_API_KEY=your_google_api_key
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_key
LANGCHAIN_PROJECT=fantasy-football-chatbot
```

**3. Database**
Ensure your SQLite database is located at: `data/llm_fantasy_data.db`

## 🚀 Usage

**Run the Chat Interface:**
```bash
streamlit run backend/app.py
```

**Run Evaluations:**
Run the conversational test suite against `data/test_set_conversations.csv`:
```bash
python backend/run_conversational_evals.py
```

## 📂 Key Files
*   **`backend/graph_builder.py`**: The Orchestrator. Contains the **Query Enhancer**, **Router**, and **Responder** nodes.
*   **`backend/utils.py`**: The Specialist. Contains the **SQL Agent Subgraph**, System Prompts, and Table Definitions.
*   **`backend/app.py`**: Streamlit frontend with Session State and **MemorySaver** persistence.