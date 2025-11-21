# 🏈 Fantasy Football Chatbot - Frontend

Streamlit-based user interface for the Fantasy Football chatbot.

## Overview

The frontend provides an interactive chat interface that communicates with the FastAPI backend to process user queries about fantasy football data.

## Setup

**1. Install Dependencies**

```bash
cd frontend
pip install -r requirements.txt
```

**2. Configuration**

The frontend expects the backend API to be running at `http://localhost:8000` by default.

To change the API URL, modify the `API_BASE_URL` variable in `app.py`.

## Running the Frontend

From the project root:

```bash
cd frontend
streamlit run app.py
```

The Streamlit app will open automatically in your browser at: http://localhost:8501

## Features

- **Chat Interface:** Interactive chat UI for asking questions
- **Conversation Memory:** Maintains conversation history within a session
- **Thread Persistence:** Uses thread IDs to maintain context across requests
- **Error Handling:** Graceful error messages for API connection issues

## Project Structure

```
frontend/
├── app.py              # Main Streamlit application
├── .streamlit/         # Streamlit configuration
├── requirements.txt    # Frontend dependencies
└── Dockerfile         # Container configuration
```

## Usage

1. Start the backend API (see backend/README.md)
2. Start the Streamlit frontend
3. Ask questions in the chat interface:
   - "Who won the championship in 2020?"
   - "What's Dylan's all-time record?"
   - "Show me the best draft picks from 2019"

## Development

The frontend uses:
- **Streamlit** for the web interface
- **httpx** for HTTP requests to the backend
- **Session state** for conversation persistence
