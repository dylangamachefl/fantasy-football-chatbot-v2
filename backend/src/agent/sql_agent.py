# --- START OF FILE sql_agent.py ---

import os
import csv
import json
import logging
import requests
import re
from typing import List, Optional
from pydantic import BaseModel, Field

# --- LangChain Imports ---
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from src.config.llm_config import LLM_API_BASE_URL, LLM_MODEL_NAME, LLM_API_KEY
from src.agent.dspy_modules import get_query_enhancer, get_table_router, get_sql_generator, get_responder
from src.agent.state import AgentState

# --- Setup ---
logger = logging.getLogger(__name__)

# Define your league members here
VALID_FANTASY_OWNERS = [
    "Dylan",
    "Dan",
    "Zach",
    "Chris",
    "Sean",
    "Jack",
    "Lac",
    "Will",
    "Josh",
    "Jake",
    "Fitz",
    "Mark",
    "Nick",
]  # <--- Replace with your actual league names


# --- Pydantic Model (Unchanged) ---
class TableSelection(BaseModel):
    tables: List[str] = Field(
        description="List of table names needed to answer the query."
    )
    reasoning: str = Field(
        description="Brief explanation of why these tables were selected"
    )


# =========================================================================
# --- Custom Safe SQL Tool (SIMPLIFIED) ---
# =========================================================================
class SafeSQLQueryTool(BaseTool):
    name: str = "sql_db_query"
    description: str = (
        "Run a SQLite query against the database. Use this to answer any user questions."
    )
    sidecar_url: str = Field(default_factory=lambda: os.environ.get("SIDECAR_URL", "http://localhost:8081"))

    def _run(self, query: str) -> str:
        try:
            resp = requests.post(f"{self.sidecar_url}/query", json={"query": query})

            # If the sidecar is down or errors, raise exception
            resp.raise_for_status()

            resp_data = resp.json()

            if resp_data.get("error"):
                 return json.dumps({"error": resp_data["error"]})

            # Return as JSON string so the Agent AND the Frontend can parse it
            return json.dumps({"columns": resp_data.get("columns", []), "data": resp_data.get("data", [])}, default=str)

        except Exception as e:
            # Return the raw error to the agent so it can self-correct
            return json.dumps({"error": f"Sidecar/Network Error: {str(e)}"})

    async def _arun(self, query: str) -> str:
        raise NotImplementedError("SafeSQLQueryTool does not support async execution.")


# =========================================================================
# --- Core Components & Data Loading ---
# =========================================================================


def get_data_path(filename: str) -> str:
    """
    Helper to resolve data file paths whether running from root or backend/
    """
    # Check current directory (e.g. running from backend/ where data/ is a subdir)
    if os.path.exists(filename):
        return filename

    # Check if running from root (need to prepend backend/)
    backend_path = os.path.join("backend", filename)
    if os.path.exists(backend_path):
        return backend_path

    # Return original and let caller handle not found
    return filename

def get_valid_table_names(filepath: str = "data/table_dictionary.csv") -> List[str]:
    resolved_path = get_data_path(filepath)
    try:
        with open(resolved_path, mode="r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            return [row["table_name"] for row in reader]
    except FileNotFoundError:
        return []
    except Exception:
        return []


_llm = None


def get_llm():
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(
            model=LLM_MODEL_NAME,
            temperature=0,
            api_key=LLM_API_KEY,
            base_url=LLM_API_BASE_URL,
        )
    return _llm


_structured_llm = None


def get_structured_llm():
    global _structured_llm
    if _structured_llm is None:
        _structured_llm = get_llm().with_structured_output(TableSelection)
    return _structured_llm


_table_descriptions_cache = None

def load_table_descriptions(filepath: str = "data/table_dictionary.csv") -> str:
    global _table_descriptions_cache
    if _table_descriptions_cache is not None:
        return _table_descriptions_cache

    resolved_path = get_data_path(filepath)
    try:
        with open(resolved_path, mode="r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            _table_descriptions_cache = "\n".join(
                [
                    f"Table: {row['table_name']}, Description: {row['table_description']}"
                    for row in reader
                ]
            )
    except Exception:
        _table_descriptions_cache = ""

    return _table_descriptions_cache


def get_detailed_schema_info(
    table_names: List[str],
    column_dict_path: str = "data/data_dictionary.csv",
    table_dict_path: str = "data/table_dictionary.csv",
) -> str:
    """
    Builds a rich schema including Table Descriptions AND Column Descriptions.
    """
    logger.info(f"Loading schema for tables: {table_names}")

    normalized_target_tables = {name.strip().lower() for name in table_names}

    # 1. Load Table Descriptions (High Level context)
    table_descriptions = {}
    resolved_table_dict = get_data_path(table_dict_path)
    try:
        with open(resolved_table_dict, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["table_name"].strip().lower() in normalized_target_tables:
                    table_descriptions[row["table_name"]] = row["table_description"]
    except Exception as e:
        logger.warning(f"Could not load table descriptions: {e}")

    # 2. Load Column Descriptions (Specific details)
    table_columns = {}
    resolved_column_dict = get_data_path(column_dict_path)
    try:
        with open(resolved_column_dict, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                t_name = row["table_name"]
                if t_name.strip().lower() in normalized_target_tables:
                    if t_name not in table_columns:
                        table_columns[t_name] = []

                    # Format: "column_name (type): description"
                    # Note: If you have types in your CSV, add them. If not, just name/desc.
                    table_columns[t_name].append(
                        f"  - {row['column_name']}: {row['column_description']}"
                    )
    except Exception as e:
        logger.error(f"Error reading column dictionary: {e}")
        # Fallback: Ask Sidecar for schema
        try:
             # We assume sidecar is at localhost:8081 for now, but should use env var in prod
             sidecar_url = os.environ.get("SIDECAR_URL", "http://localhost:8081")
             resp = requests.get(f"{sidecar_url}/schema", params={"table_names": table_names})
             if resp.status_code == 200:
                 return resp.json().get("schema", "No schema found.")
        except Exception as sidecar_err:
             logger.error(f"Sidecar schema fetch failed: {sidecar_err}")

        return "Error loading detailed schema info."

    # 3. Construct the Final String
    schema_parts = ["=" * 50, "DATABASE SCHEMA", "=" * 50]

    for t_name in table_names:
        # Only process tables we actually found info for
        if t_name in table_descriptions or t_name in table_columns:
            schema_parts.append(f"\n📄 TABLE: {t_name}")

            # Add Table Description (The Context)
            desc = table_descriptions.get(t_name, "No description available.")
            schema_parts.append(f"   Description: {desc}")
            schema_parts.append(f"   Columns:")

            # Add Column Descriptions
            cols = table_columns.get(t_name, [])
            if cols:
                schema_parts.extend(cols)
            else:
                # Fallback removed
                schema_parts.append("   No column info found.")

    schema_parts.append("\n" + "=" * 50)
    return "\n".join(schema_parts)

# =========================================================================
# --- Nodes ---
# =========================================================================

def node_greeting_handler(state: AgentState):
    """
    Handles simple greetings without invoking the heavy chain.
    """
    return {"messages": [AIMessage(content="Hello! I'm your Fantasy Football Assistant. Ask me anything about your league history, stats, or matchups!")]}

def node_query_enhancer(state: AgentState):
    """
    Enhances the user's query using DSPy.
    """
    raw_input = state["raw_input"]
    history = [m.content for m in state["messages"][:-1]] if state.get("messages") else []
    
    enhancer = get_query_enhancer()
    result = enhancer(history=str(history), user_query=raw_input)

    # Store in enhanced_input, keep raw_input immutable
    return {"enhanced_input": result.enhanced_query}

def node_table_router(state: AgentState):
    """
    Selects tables based on the enhanced query using DSPy or LLM.
    """
    # Use enhanced input for routing
    query = state.get("enhanced_input") or state["raw_input"]

    # Identify explicit owner mentions for the 'hint'
    # Use robust token-based matching to avoid false positives (e.g. "Dan" in "Dancing")
    query_tokens = set(re.findall(r"\b\w+\b", query.lower()))
    detected_owners = [
        owner for owner in VALID_FANTASY_OWNERS
        if owner.lower() in query_tokens
    ]
    hint = f"Detected Owners: {', '.join(detected_owners)}" if detected_owners else "No owners detected."

    router = get_table_router()
    # Core tables
    core_tables = ["FantasyOwners_LLM", "FantasySeasons_LLM", "FantasyTeams_LLM", "FantasyMatchups_LLM"]

    # Get available tables description
    table_desc = load_table_descriptions()

    result = router(user_query=query, table_descriptions=table_desc, hint=hint)

    # Merge core tables with selected specialty tables
    # Ensure result.selected_tables is a list
    selected = result.selected_tables
    if isinstance(selected, str):
        # Fallback if dspy returns a string representation of list
        try:
            import ast
            selected = ast.literal_eval(selected)
        except:
             selected = []

    final_tables = list(set(core_tables + selected))

    return {
        "selected_tables": final_tables,
        "table_selection_reasoning": result.reasoning
    }

def node_schema_builder(state: AgentState):
    """
    Builds the detailed schema string for the selected tables.
    """
    tables = state["selected_tables"]
    schema_info = get_detailed_schema_info(tables)
    return {"forced_schema": schema_info}

def node_sql_generator(state: AgentState):
    """
    Generates the SQL query using DSPy.
    Handles retries if an error exists in the state.
    """
    query = state.get("enhanced_input") or state["raw_input"]
    schema = state["forced_schema"]

    # Check for previous error to handle retry
    previous_error = state.get("error")
    previous_sql = state.get("sql_query")

    generator = get_sql_generator()

    # If retrying, pass previous context
    if previous_error:
        logger.info(f"Retrying SQL generation. Error: {previous_error}")
        result = generator(
            question=query,
            db_schema=schema,
            previous_sql=previous_sql,
            error_message=previous_error
        )
    else:
        result = generator(question=query, db_schema=schema)

    return {
        "sql_query": result.sql_query,
        # Increment retry count if we are retrying?
        # Actually retry_count is incremented in the conditional edge logic usually,
        # or we can increment it here if we know we are in a retry loop.
        # But for state updates, we just return the new SQL.
        # We will manage retry_count increment in the graph edge logic or here if we want to be explicit.
        # Let's just update the query. The edge check decides based on count.
        # Wait, if I don't increment retry_count, the edge check won't know when to stop.
        # But the edge check *reads* the count. Something needs to increment it.
        # If I am here because of a retry, I should probably have incremented it *before* coming here?
        # Or I increment it here if previous_error is present.
        "retry_count": state["retry_count"] + 1 if previous_error else state["retry_count"]
    }

def node_sql_executor(state: AgentState):
    """
    Executes the generated SQL using the SafeSQLQueryTool.
    """
    query = state["sql_query"]

    # Clean the SQL (remove markdown blocks if present)
    clean_query = query.strip()
    if clean_query.startswith("```sql"):
        clean_query = clean_query[6:]
    if clean_query.startswith("```"):
        clean_query = clean_query[3:]
    if clean_query.endswith("```"):
        clean_query = clean_query[:-3]
    clean_query = clean_query.strip()

    tool = SafeSQLQueryTool()

    # Execute
    result_json = tool._run(clean_query) # tool._run returns JSON string

    try:
        result_data = json.loads(result_json)
    except:
        result_data = {"error": "Failed to parse tool output"}

    if "error" in result_data:
        return {
            "error": result_data["error"],
            "sql_result": "" # Clear result on error
        }
    else:
        # Success
        return {
            "sql_result": result_json, # Keep the full JSON string for the responder
            "error": None # Clear error
        }

def node_responder(state: AgentState):
    """
    Generates the final natural language response.
    """
    query = state.get("enhanced_input") or state["raw_input"]
    history = [m.content for m in state["messages"]] if state.get("messages") else []

    # If we have an error after retries
    if state.get("error"):
        return {"messages": [AIMessage(content=f"I encountered an error while trying to answer your question: {state['error']}")], "retry_count": 0}

    data_context = state["sql_result"]

    # If data is empty (but no error), we might want to handle it gracefully
    # The JSON structure is {"columns": [...], "data": [...]}
    try:
        parsed = json.loads(data_context)
        if not parsed.get("data"):
            # Empty result
            # We can let the responder handle "No data found"
            pass
    except:
        pass

    responder = get_responder()
    result = responder(history=str(history), data_context=data_context)

    return {
        "messages": [AIMessage(content=result.answer)],
        "retry_count": 0, # Reset retry count after success
        "error": None
    }
