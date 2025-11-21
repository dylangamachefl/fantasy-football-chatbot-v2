# Running the Fantasy Football Chatbot

This application now uses a client-server architecture with a FastAPI backend and Streamlit frontend.

## Prerequisites

Install dependencies:
```bash
cd backend
pip install -r requirements.txt
```

## Starting the Application

You need to run **both** services in separate terminal windows:

### 1. Start the FastAPI Backend

```bash
cd backend
uvicorn api:app --reload --port 8000
```

The API will be available at: http://localhost:8000
- Health check: http://localhost:8000/health
- API docs: http://localhost:8000/docs

### 2. Start the Streamlit Frontend

In a **new terminal window**:

```bash
cd backend
streamlit run app.py
```

The Streamlit app will open automatically in your browser at: http://localhost:8501

## How It Works

- The **Streamlit frontend** (`app.py`) provides the user interface
- The **FastAPI backend** (`api.py`) handles the LangGraph workflow and AI processing
- The frontend communicates with the backend via HTTP POST requests to `/chat`
- Conversation history is maintained using thread IDs stored in the API's memory

## Troubleshooting

If you see "Cannot connect to the API" in the Streamlit app:
1. Make sure the FastAPI backend is running on port 8000
2. Check that there are no firewall issues blocking localhost connections
3. Verify the API is responding by visiting http://localhost:8000/health
