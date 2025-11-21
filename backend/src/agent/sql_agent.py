# --- START OF FILE sql_agent.py ---

import os
import csv
import logging
import streamlit as st
from typing import List
from pydantic import BaseModel, Field

# --- LangChain Imports ---
from langchain.agents import create_agent
from langchain_community.utilities import SQLDatabase
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import SystemMessage

# --- SQL Parsing Library ---
import sqlglot
from sqlglot import exp

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
    db: SQLDatabase

    def _run(self, query: str) -> str:
        try:
            # 1. Parse only to ensure it is syntactically valid SQL
            parsed_query = sqlglot.parse_one(query, read="sqlite")
            if not parsed_query:
                return "Error: The provided SQL query is invalid or empty. Please check your syntax."

            # 2. Security Check: Ensure it is a SELECT statement
            # We iterate through all expressions to make sure there are no modification commands
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
                    return "Error: You are only allowed to execute SELECT queries."

            # 3. Execution: Trust the Database
            # We rely on SQLite to throw an error if columns/tables don't exist.
            # The Agent is capable of reading that error and fixing its own query.
            return self.db.run(query)

        except Exception as e:
            # Return the raw database error to the agent so it can self-correct
            return f"Database Error: {str(e)}"

    async def _arun(self, query: str) -> str:
        raise NotImplementedError("SafeSQLQueryTool does not support async execution.")


# =========================================================================
# --- Core Components & Data Loading ---
# =========================================================================


def get_data_path(filename: str) -> str:
    """
    Helper to resolve data file paths whether running from root or backend/
    """
    # Check current directory (root case)
    if os.path.exists(filename):
        return filename

    # Check if running from backend/ (parent directory has data)
    if os.path.exists(os.path.join("..", filename)):
        return os.path.join("..", filename)

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
        # Try environment variable first, then fallback to streamlit secrets
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            try:
                api_key = st.secrets["GOOGLE_API_KEY"]
            except Exception:
                raise ValueError("GOOGLE_API_KEY not found in environment variables or st.secrets")

        _llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite",
            temperature=0,
            google_api_key=api_key,
        )
    return _llm


_structured_llm = None


def get_structured_llm():
    global _structured_llm
    if _structured_llm is None:
        _structured_llm = get_llm().with_structured_output(TableSelection)
    return _structured_llm


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


def load_table_descriptions(filepath: str = "data/table_dictionary.csv") -> str:
    resolved_path = get_data_path(filepath)
    try:
        with open(resolved_path, mode="r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            return "\n".join(
                [
                    f"Table: {row['table_name']}, Description: {row['table_description']}"
                    for row in reader
                ]
            )
    except Exception:
        return ""


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
        # Fallback: If CSV fails, use the basic SQL engine schema
        return get_db().get_table_info(table_names)

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
                # Fallback if we have table desc but no column CSV data
                # We can ask the DB for raw columns
                try:
                    raw_schema = get_db().get_table_info([t_name])
                    schema_parts.append(f"   (Using raw DDL)\n{raw_schema}")
                except:
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
    db = get_db()

    tools = [SafeSQLQueryTool(db=db)]
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
