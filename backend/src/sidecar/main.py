import os
import csv
import json
import logging
from typing import List
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from langchain_community.utilities import SQLDatabase
import sqlglot
from sqlglot import exp

from .models import QueryRequest, QueryResponse

# --- Setup ---
logger = logging.getLogger("sidecar")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="SQL Sidecar")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Database Helper Functions ---

def get_base_dir() -> Path:
    """Returns the backend directory path."""
    # Current file is backend/src/sidecar/main.py
    # We want backend/
    current_file = Path(__file__).resolve()
    return current_file.parent.parent.parent

def get_data_path(filename: str) -> str:
    """
    Helper to resolve data file paths.
    Tries to find the file relative to the backend root.
    """
    base_dir = get_base_dir()

    # If filename starts with data/, we assume it is inside backend/data/
    # If filename starts with backend/data/, strip backend/

    clean_filename = filename
    if filename.startswith("backend/"):
        clean_filename = filename.replace("backend/", "", 1)

    path = base_dir / clean_filename
    if path.exists():
        return str(path)

    # Fallback to checking if we are in repo root and filename works as is
    if os.path.exists(filename):
        return filename

    # Fallback for "backend/..." if we are in root
    if os.path.exists(f"backend/{clean_filename}"):
        return f"backend/{clean_filename}"

    return str(path)

def get_valid_table_names(filepath: str = "data/table_dictionary.csv") -> List[str]:
    resolved_path = get_data_path(filepath)
    try:
        with open(resolved_path, mode="r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            return [row["table_name"] for row in reader]
    except FileNotFoundError:
        logger.error(f"Table dictionary not found at {resolved_path}")
        return []
    except Exception as e:
        logger.error(f"Error reading table dictionary: {e}")
        return []

_db = None

def get_db():
    global _db
    if _db is None:
        db_path = get_data_path("data/llm_fantasy_data.db")
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database file '{db_path}' not found.")

        # Set mode=ro (Read Only) to ensure database integrity at the connection level
        db_uri = f"sqlite:///{db_path}?mode=ro"

        valid_tables = get_valid_table_names()
        if not valid_tables:
            raise ValueError("No valid tables found.")

        _db = SQLDatabase.from_uri(
            db_uri,
            include_tables=valid_tables,
            sample_rows_in_table_info=0,
            lazy_table_reflection=True,
            view_support=True,
        )
    return _db

# --- Endpoints ---

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/schema")
async def get_schema(table_names: List[str] = Query(None)):
    """
    Returns schema information. If table_names is provided, returns info for those tables.
    Otherwise returns info for all valid tables.
    """
    try:
        if not table_names:
            table_names = get_valid_table_names()

        db = get_db()
        # Fallback to getting table info from DB if CSV is missing or partial
        # This provides the raw DDL
        schema_info = db.get_table_info(table_names)
        return {"schema": schema_info}
    except Exception as e:
        logger.error(f"Error fetching schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/query", response_model=QueryResponse)
async def execute_query(payload: QueryRequest):
    """
    Executes a SQL query against the database with safety checks.
    """
    query = payload.query
    logger.info(f"Received query: {query}")

    try:
        # 1. Parse only to ensure it is syntactically valid SQL
        parsed_query = sqlglot.parse_one(query, read="sqlite")
        if not parsed_query:
             raise ValueError("The provided SQL query is invalid or empty.")

        # 2. Security Check: Ensure it is a SELECT statement
        for node in parsed_query.walk():
            if isinstance(
                node,
                (
                    exp.Insert,
                    exp.Update,
                    exp.Delete,
                    exp.Drop,
                    exp.Create,
                    exp.Alter,
                ),
            ):
                raise ValueError("Error: You are only allowed to execute SELECT queries.")

        # 3. Execution
        db = get_db()
        # Use the engine directly to ensure we get the result proxy.
        with db._engine.connect() as connection:
            result = connection.execute(text(query))

            # Extract columns and rows
            columns = list(result.keys())
            rows = [dict(row._mapping) for row in result.fetchall()]

        return QueryResponse(columns=columns, data=rows)

    except Exception as e:
        logger.error(f"Query execution failed: {e}")
        # We return the error in the response field instead of HTTP 500
        # because the agent expects to see the error message to self-correct.
        return QueryResponse(columns=[], data=[], error=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
