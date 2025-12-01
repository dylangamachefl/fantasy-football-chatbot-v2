# --- START OF FILE sql_agent.py ---

import os
import csv
import json
import logging
import requests
from typing import List
from pydantic import BaseModel, Field

# --- LangChain Imports ---
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import SystemMessage
from src.config.llm_config import LLM_API_BASE_URL, LLM_MODEL_NAME, LLM_API_KEY

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
    sidecar_url: str = "http://localhost:8081"

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
             sidecar_url = "http://localhost:8081"
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
# --- Agent Creation ---
# =========================================================================


def build_sql_agent_graph(forced_schema: str):
    """
    Builds a pure LangGraph v1 StateGraph for the SQL Agent.
    """
    llm = get_llm()

    tools = [SafeSQLQueryTool()]
    llm_with_tools = llm.bind_tools(tools)

    system_message_content = f"""You are an expert SQLite data analyst. 

**YOUR GOAL:** 
Using only the tables and columns provided to you generate a correct SQL query and execute it immediately. Do NOT attempt to answer without executing a query. Do NOT try to use tables or columns that are not listed in the schema.

1. **Follow-up Questions:** When the user sends a message, you MUST look at the **Conversation History** to understand the context. 

**MANDATORY PROCESS:**
1. **THOUGHT:** Write EXACTLY ONE sentence explaining your logic.
2. **ACTION:** Call the `sql_db_query` tool.
3. **CHECK:** 
   - If the tool returns **DATA**: STOP. Do not talk.
   - If the tool returns an **ERROR**: **Do Not stop.** Read the error message carefully, fix your SQL logic, and call the tool again.

**NEGATIVE CONSTRAINTS (What NOT to do):**
- **DO NOT** give up. If you get a syntax error, try a simpler query or check column names.
- **DO NOT** write "EXECUTE:" or "I will now...".
- **DO NOT** repeat your plan.
- **DO NOT** write pseudo-code or explain the query in detail. Just run it.
- **DO NOT** loop or restate valid owners.

**SQL RECIPES (Use these EXACT patterns):**

**1. HEAD-TO-HEAD RECORDS (e.g., "Dylan vs Dan"):**
   - **Pattern:** You MUST use `CASE WHEN` on the `winning_owner_id` to count wins.
   - **Template:**
     ```sql
     SELECT 
       SUM(CASE WHEN winning_owner_id = (SELECT owner_id FROM FantasyOwners_LLM WHERE owner_name = 'OwnerA') THEN 1 ELSE 0 END) AS OwnerA_Wins,
       SUM(CASE WHEN winning_owner_id = (SELECT owner_id FROM FantasyOwners_LLM WHERE owner_name = 'OwnerB') THEN 1 ELSE 0 END) AS OwnerB_Wins,
       COUNT(CASE WHEN tie = 1 THEN 1 END) AS Ties
     FROM HeadToHeadMatchups_LLM
     WHERE matchup_category = 'Regular Season'
       AND (
         (owner1_id = (SELECT owner_id FROM FantasyOwners_LLM WHERE owner_name = 'OwnerA') AND owner2_id = (SELECT owner_id FROM FantasyOwners_LLM WHERE owner_name = 'OwnerB'))
         OR 
         (owner1_id = (SELECT owner_id FROM FantasyOwners_LLM WHERE owner_name = 'OwnerB') AND owner2_id = (SELECT owner_id FROM FantasyOwners_LLM WHERE owner_name = 'OwnerA'))
       );
     ```

**CRITICAL SQL RULES:**
1. **Head-to-Head:** NEVER join `FantasyOwners_LLM` to `HeadToHeadMatchups_LLM` with `OR`. Filter directly.

2. **THE "TOP 10" MANDATE (CRITICAL):**
   - **NEVER use `LIMIT 1` for "most", "winner", "highest", or "best" queries.**
   - **Reason:** In this specific database, TIES are extremely common. If you use `LIMIT 1`, you will miss tied winners and return INCORRECT results.
   - **Requirement:** You MUST use **`LIMIT 10`** (or higher) for any ranking query.
   - *Self-Correction:* If you find yourself writing `LIMIT 1`, STOP. Change it to `LIMIT 10`.
   - Including extra rows is acceptable; missing tied results is expensive.
    
3. **Limit Exceptions:**
   - Use NO LIMIT if the user asks for "all", "list", or "average/sum".

4. **Smart Name Matching:**
   - Users often use nicknames (e.g. "CMC", "Mahomes", "JJ").
   - **NEVER** assume an exact match for player names.
   - **STRATEGY:** Use `LIKE '%Name%'` OR check the `Players_LLM` table first to find the correct `player_name`.
   - *Example:* `WHERE player_name LIKE '%Mahomes%'` is safer than `= 'Patrick Mahomes'`.

5. **Valid Owners:** The ONLY valid values for `owner_name` are: **{VALID_FANTASY_OWNERS}**.
    - If the user says "Chris" (and it's in the owner list), assume they mean the Owner, NOT the NFL player "Chris Godwin".

6. Always use the owners name to get the owner_id from the `FantasyOwners_LLM` table. The owner_id will be used to join against other tables.

7. **NO RAW IDs:** 
   - NEVER return an `owner_id`, `team_id`, or `matchup_id` alone. 
   - **ALWAYS JOIN** to `FantasyOwners_LLM` to get the `owner_name`.
   - *Bad:* `SELECT away_owner_id...` -> Returns "6".
   - *Good:* `SELECT T2.owner_name... JOIN FantasyOwners_LLM T2 ON T1.away_owner_id = T2.owner_id`.

8. **AGGREGATION RULE (The "Who" Rule):**
   - When calculating `MAX()`, `MIN()`, or `LIMIT 1`, you **MUST** select the `owner_name` or `team_name` column too.
   - *Bad:* `SELECT MAX(points) FROM...` -> Returns "150". (We don't know who scored it).
   - *Good:* `SELECT owner_name, points FROM... ORDER BY points DESC LIMIT 1`.

9. **LOGIC DEFINITIONS:**
   - **"Runner-Up":** Means `final_standing = 2`. (Do NOT use `ORDER BY DESC`).
   - **"Champion/Winner":** Means `final_standing = 1`.
   - **"Last Place":** Means `MAX(final_standing)`.

10. **Head-to-Head:**
   - Pattern: Use `CASE WHEN winning_owner_id = ...` logic defined previously.
   - Never use `OR` joins on owners.

{forced_schema}
"""
    sys_msg = SystemMessage(content=system_message_content)

    def call_model(state: MessagesState):
        messages = [sys_msg] + state["messages"]
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    workflow = StateGraph(MessagesState)
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", ToolNode(tools))
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", tools_condition)
    workflow.add_edge("tools", "agent")

    return workflow.compile()
