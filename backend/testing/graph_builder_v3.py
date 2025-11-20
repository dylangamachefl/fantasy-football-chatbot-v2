# --- graph_builder_v3.py ---
# Fixed planner context and conditional logic bug

import os
import csv
import logging
import re
import sqlparse
from typing import List, Dict, Any, Optional, Set
from pydantic import BaseModel, Field

# --- LANGCHAIN IMPORTS ---
from langgraph.graph import StateGraph, END
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import (
    BaseMessage,
    AIMessage,
    HumanMessage,
    ToolMessage,
    SystemMessage,
)
from langchain_community.tools.sql_database.tool import QuerySQLDatabaseTool
from langchain_community.utilities import SQLDatabase
from langchain_google_genai import ChatGoogleGenerativeAI

# --- Import our UPDATED Agent State ---
from agent_state_v3 import (
    AgentState,
    QueryMetadata,
    ConversationTurn,
    create_initial_state,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# =========================================================================
# --- PYDANTIC MODELS (Unchanged) ---
# =========================================================================
class SmartRouterOutput(BaseModel):
    query_type: str = Field(
        description="Type of query: 'greeting', 'simple_query', 'complex_query', 'follow_up'"
    )
    enhanced_query: str = Field(
        description="Query with pronouns resolved and context added"
    )
    selected_tables: List[str] = Field(
        description="List of table names needed to answer the query"
    )
    reasoning: str = Field(description="Brief explanation of analysis")
    needs_planning: bool = Field(
        description="Whether this query needs multi-step planning"
    )
    complexity_score: int = Field(description="Query complexity on 1-10 scale")
    entities: Dict[str, str] = Field(
        description="Key entities mentioned (person, season, etc.)",
        default_factory=dict,
    )
    quick_response: Optional[str] = Field(
        description="Direct response for greetings/simple queries", default=None
    )


class QueryPlan(BaseModel):
    strategy: str = Field(description="High-level approach to answer the query")
    steps: List[str] = Field(description="Ordered steps to execute")
    estimated_queries: int = Field(description="Expected number of SQL queries")


class FormatterOutput(BaseModel):
    final_answer: str = Field(description="Natural language answer for user")
    sql_summary: str = Field(description="Summary of SQL queries executed")
    entities_to_save: Dict[str, str] = Field(
        description="Key entities to remember for next turn", default_factory=dict
    )


# =========================================================================
# --- HELPER FUNCTIONS (Unchanged) ---
# =========================================================================
def get_llm():
    return ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0)


def get_structured_llm_router():
    return get_llm().with_structured_output(SmartRouterOutput)


def get_structured_llm_planner():
    return get_llm().with_structured_output(QueryPlan)


def get_structured_llm_formatter():
    return get_llm().with_structured_output(FormatterOutput)


def get_db():
    db_uri = f"sqlite:///{'data/llm_fantasy_data.db'}?mode=ro"
    return SQLDatabase.from_uri(
        db_uri,
        sample_rows_in_table_info=0,
        lazy_table_reflection=True,
        view_support=True,
    )


def load_table_descriptions(filepath: str) -> str:
    try:
        with open(filepath, mode="r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            return "\n".join(
                [
                    f"Table: {row['table_name']}, Description: {row['table_description']}"
                    for row in reader
                ]
            )
    except Exception as e:
        logger.error(f"Failed to load table dictionary: {e}")
        return ""


def get_detailed_schema_info(
    table_names: List[str], filepath: str = "data/data_dictionary.csv"
) -> str:
    try:
        with open(filepath, mode="r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            all_rows = list(reader)
            normalized_target_tables = {name.strip().lower() for name in table_names}
            relevant_rows = [
                row
                for row in all_rows
                if row["table_name"].strip().lower() in normalized_target_tables
            ]
            if not relevant_rows:
                return db.get_table_info(table_names=table_names)
            table_schemas = {}
            for row in relevant_rows:
                table_name = row["table_name"]
                if table_name not in table_schemas:
                    table_schemas[table_name] = []
                col_info = f"  • {row['column_name']}: {row['column_description']}"
                table_schemas[table_name].append(col_info)
            schema_parts = [
                "=" * 70,
                "DATABASE SCHEMA - AVAILABLE TABLES AND COLUMNS",
                "=" * 70,
                "",
            ]
            for table, columns in table_schemas.items():
                schema_parts.append(f"📊 Table: {table}")
                schema_parts.extend(columns)
                schema_parts.append("")
            schema_parts.extend(
                [
                    "=" * 70,
                    "IMPORTANT: Do not reference any tables or columns not listed above.",
                    "=" * 70,
                ]
            )
            return "\n".join(schema_parts)
    except Exception as e:
        logger.error(f"Error loading schema: {e}")
        return db.get_table_info(table_names=table_names)


# =========================================================================
# --- SQL VALIDATOR & COMPLEXITY (Unchanged) ---
# =========================================================================
def validate_sql_query(
    query: str, allowed_tables: List[str], schema_info: str
) -> tuple[bool, Optional[str]]:
    dangerous_keywords = [
        "DROP",
        "DELETE",
        "UPDATE",
        "INSERT",
        "ALTER",
        "CREATE",
        "TRUNCATE",
    ]
    query_upper = query.upper()
    for keyword in dangerous_keywords:
        if keyword in query_upper:
            return False, f"Dangerous keyword '{keyword}' not allowed in read-only mode"
    try:
        sqlparse.parse(query)
    except Exception as e:
        return False, f"SQL syntax error: {str(e)}"

    referenced_tables = set(
        re.findall(
            r"FROM\s+([a-zA-Z0-9_]+)|JOIN\s+([a-zA-Z0-9_]+)", query, re.IGNORECASE
        )
    )
    referenced_tables = {t for tup in referenced_tables for t in tup if t}

    allowed_tables_lower = {t.lower() for t in allowed_tables}
    for table in referenced_tables:
        if table.lower() not in allowed_tables_lower:
            return (
                False,
                f"Table '{table}' not in selected tables. Available: {allowed_tables}",
            )

    if "SELECT" not in query_upper:
        return False, "Query must be a SELECT statement"
    return True, None


def calculate_complexity_score(query: str, num_tables: int) -> int:
    score = num_tables
    query_lower = query.lower()
    if any(kw in query_lower for kw in ["compare", "versus", "vs", "difference"]):
        score += 2
    if any(kw in query_lower for kw in ["trend", "over time", "across seasons"]):
        score += 2
    agg_count = sum(
        query_lower.count(kw) for kw in ["avg", "sum", "count", "max", "min"]
    )
    score += min(agg_count, 3)
    return min(score, 10)


# =========================================================================
# --- AGENT INITIALIZATION (Unchanged) ---
# =========================================================================
llm = get_llm()
router_llm = get_structured_llm_router()
planner_llm = get_structured_llm_planner()
formatter_llm = get_structured_llm_formatter()
db = get_db()
sql_tool = QuerySQLDatabaseTool(db=db)
tools = [sql_tool]
tool_map = {"sql_db_query": sql_tool}
table_descriptions = load_table_descriptions("data/table_dictionary.csv")
llm_with_tools = llm.bind_tools(tools)

# =========================================================================
# --- AGENT PROMPTS (Unchanged from provided file) ---
# =========================================================================
smart_router_prompt = ChatPromptTemplate.from_template(
    f"""You are an intelligent query analyzer for a fantasy football database assistant.
Your goal is to understand the user's query, enrich it with conversation context, and determine the best tables and strategy to answer it.

**CONVERSATION HISTORY:**
{{conversation_history}}

**CURRENT CONTEXT (entities mentioned):**
{{current_context}}

**AVAILABLE TABLES:**
{table_descriptions}

Based on this, analyze the user's query below.

**USER'S QUERY:**
"{{user_query}}"

**YOUR TASK:**
1.  **Resolve Context:** Rewrite the user's query to be a standalone question. Resolve pronouns (like "he", "their") using the conversation history and current context.
2.  **Select Tables:** Identify the minimum set of tables required from the "AVAILABLE TABLES" list.
3.  **Determine Type:** Classify the query as 'greeting', 'simple_query' (one table, simple aggregation), 'complex_query' (multiple tables, complex logic), or 'follow_up'.
4.  **Assess Complexity:** On a scale of 1-10, how complex is this query?
5.  **Plan Needed?:** Does this query require a multi-step plan (e.g., finding a list of players first, then getting their stats)?
6.  **Extract Entities:** List any specific entities like player names, owner names, or seasons.
7.  **Quick Response:** If it's a greeting or a very simple question you can answer without a database lookup, provide a direct answer.
"""
)

planner_prompt = ChatPromptTemplate.from_template(
    """You are a query planning expert for SQL databases.
Given a complex query and the available database schema, create a high-level strategy to answer it efficiently.

**USER QUERY:** {enhanced_query}

**AVAILABLE SCHEMA (Tables and Columns):**
{schema_info}

**TASK:**
Break down the approach into clear steps. Do NOT write SQL - just describe the strategy using the available columns.
"""
)

system_prompt_string = """You are an expert SQLite data analyst. Your job is to gather all data needed to answer a user's question by writing and executing SQL queries.

**CRITICAL RULES:**
1.  This is SQLite - use ONLY SQLite syntax.
2.  **CRITICAL:** Only use tables and columns explicitly listed in the schema provided.
3.  **CRITICAL:** DO NOT invent table names. If you need standings/rankings, calculate them from available tables.
4.  If a query fails, read the error message and fix it. Do not apologize. Just fix the query and try again.

{query_plan}

**YOUR GOAL:**
Call the `sql_db_query` tool to gather all necessary data. You do NOT need to synthesize the final answer. Another agent will do that.

**WHEN YOU HAVE ALL THE DATA:**
Your FINAL message should be:
"Data gathered. Proceeding to synthesis."
"""

agent_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system_prompt_string),
        ("system", "DATABASE SCHEMA:\n{schema_info}"),
        MessagesPlaceholder(variable_name="messages"),
    ]
)
agent_chain = agent_prompt | llm_with_tools

synthesizer_prompt = ChatPromptTemplate.from_template(
    """You are an expert fantasy football analyst. Your job is to answer the user's question in natural language, based on the data-gathering steps provided.

**USER'S QUESTION (context-aware):**
{enhanced_query}

**DATA GATHERED (SQL QUERIES & RESULTS):**
{sql_queries_with_results}

**AGENT'S FINAL THOUGHTS (for context):**
{agent_final_message}

**TASK:**
Review the user's question and the data gathered. Synthesize a clear, concise, and friendly natural language answer.
- If the data is empty or an error occurred, politely state that you couldn't find the information.
- Do NOT include the SQL queries in your answer. Just provide the answer.

**FINAL ANSWER:**
"""
)

formatter_prompt = ChatPromptTemplate.from_template(
    """You are a response formatter for a fantasy football assistant.

**TASK:** Format the final answer AND extract entities for conversation memory.

**USER'S QUESTION (context-aware):** {enhanced_query}

**SYNTHESIZED ANSWER (from analyst):**
{synthesized_answer}

**SQL QUERIES EXECUTED:**
{sql_queries}

Provide a JSON object with `final_answer`, `sql_summary`, and `entities_to_save`.
"""
)


# =========================================================================
# --- NODES (Unchanged from provided file, except where noted)---
# =========================================================================
def node_smart_router(state: AgentState) -> dict:
    logger.info("=== SMART ROUTER: Starting ===")
    prompt = smart_router_prompt.invoke(
        {
            "conversation_history": "\n".join(
                [
                    f"Q: {t['query']}\nA: {t['answer']}"
                    for t in state.get("conversation_history", [])
                ]
            ),
            "current_context": str(state.get("current_context", {})),
            "user_query": state["input"],
        }
    )
    try:
        result: SmartRouterOutput = router_llm.invoke(prompt)
        complexity = calculate_complexity_score(
            result.enhanced_query, len(result.selected_tables)
        )
        updates = {
            "query_type": result.query_type,
            "enhanced_query": result.enhanced_query,
            "selected_tables": result.selected_tables,
            "table_selection_reasoning": result.reasoning,
            "needs_planning": result.needs_planning or complexity > 6,
            "complexity_score": max(complexity, result.complexity_score),
            "current_context": {**state.get("current_context", {}), **result.entities},
        }
        if result.query_type == "greeting" and result.quick_response:
            updates["final_answer"] = result.quick_response
        else:
            updates["messages"] = [HumanMessage(content=result.enhanced_query)]
        return updates
    except Exception as e:
        logger.error(f"Smart Router failed: {e}")
        return {
            "query_type": "simple_query",
            "enhanced_query": state["input"],
            "selected_tables": [],
            "needs_planning": False,
            "messages": [HumanMessage(content=state["input"])],
        }


def node_schema_builder(state: AgentState) -> dict:
    logger.info("=== SCHEMA BUILDER: Loading and saving schema ===")
    forced_schema = get_detailed_schema_info(table_names=state["selected_tables"])
    return {"schema_info": forced_schema}


def node_query_planner(state: AgentState) -> dict:
    logger.info("=== QUERY PLANNER: Creating strategy ===")
    prompt = planner_prompt.invoke(
        {"enhanced_query": state["enhanced_query"], "schema_info": state["schema_info"]}
    )
    try:
        plan: QueryPlan = planner_llm.invoke(prompt)
        return {"query_plan": plan.strategy, "plan_steps": plan.steps}
    except Exception as e:
        logger.error(f"Planning failed: {e}")
        return {"query_plan": "Direct query approach"}


def node_tool_calling_agent(state: AgentState) -> dict:
    logger.info(f"=== REACT AGENT: Iteration {state['iteration_count']} ===")
    if state["iteration_count"] >= 10:
        logger.warning("Max iterations reached!")
        return {
            "messages": [
                AIMessage(content="Query too complex. Proceeding to synthesis.")
            ]
        }

    plan_context = ""
    if state.get("query_plan"):
        plan_context = f"\n\n**SUGGESTED STRATEGY:**\n{state['query_plan']}\n"

    llm_response = agent_chain.invoke(
        {
            "schema_info": state["schema_info"],
            "query_plan": plan_context,
            "messages": state["messages"],
        }
    )
    return {"messages": [llm_response], "iteration_count": state["iteration_count"] + 1}


def node_sql_validator(state: AgentState) -> dict:
    logger.info("=== SQL VALIDATOR: Checking queries ===")
    last_message = state["messages"][-1]
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {}

    validation_errors = []
    for tool_call in last_message.tool_calls:
        if tool_call["name"] == "sql_db_query":
            query = tool_call["args"].get("query", "")
            is_valid, error = validate_sql_query(
                query, state["selected_tables"], state["schema_info"]
            )
            if not is_valid:
                validation_errors.append(
                    f"Query validation failed: {error}\nQuery: {query}"
                )
                logger.warning(f"Validation error: {error}")

    if validation_errors:
        error_message = ToolMessage(
            content=f"VALIDATION ERROR: {validation_errors[0]}\nPlease revise your query.",
            tool_call_id=last_message.tool_calls[0]["id"],
        )
        return {
            "validation_errors": state.get("validation_errors", []) + validation_errors,
            "messages": [error_message],
        }

    return {}


def node_tool_executor(state: AgentState) -> dict:
    logger.info("=== TOOL EXECUTOR: Running queries ===")
    last_message = state["messages"][-1]
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {}

    tool_messages = []
    query_metadata = state.get("executed_queries", [])
    for tool_call in last_message.tool_calls:
        try:
            start_time = time.time()
            tool_output = tool_map[tool_call["name"]].invoke(tool_call["args"])
            execution_time = (time.time() - start_time) * 1000
            rows_returned = str(tool_output).count("\n") if tool_output else 0
            metadata = QueryMetadata(
                query_text=tool_call["args"].get("query", ""),
                query_result=str(tool_output),
                execution_time_ms=execution_time,
                rows_returned=rows_returned,
                tables_used=state["selected_tables"],
                success=True,
                error_message=None,
            )
            query_metadata.append(metadata)
            tool_messages.append(
                ToolMessage(content=str(tool_output), tool_call_id=tool_call["id"])
            )
        except Exception as e:
            metadata = QueryMetadata(
                query_text=tool_call["args"].get("query", ""),
                query_result=f"Error: {e}",
                execution_time_ms=0,
                rows_returned=0,
                tables_used=state["selected_tables"],
                success=False,
                error_message=str(e),
            )
            query_metadata.append(metadata)
            tool_messages.append(
                ToolMessage(
                    content=f"Error executing tool: {e}", tool_call_id=tool_call["id"]
                )
            )
    return {"messages": tool_messages, "executed_queries": query_metadata}


def node_answer_synthesizer(state: AgentState) -> dict:
    logger.info("=== ANSWER SYNTHESIZER: Generating answer ===")
    sql_results_str = "\n".join(
        [
            f"Query: {q['query_text']}\nResult: {q['query_result']}"
            for q in state.get("executed_queries", [])
        ]
    )
    if not sql_results_str:
        sql_results_str = "No data was gathered."

    prompt = synthesizer_prompt.invoke(
        {
            "enhanced_query": state.get("enhanced_query", state["input"]),
            "sql_queries_with_results": sql_results_str,
            "agent_final_message": state["messages"][-1].content,
        }
    )
    try:
        response = llm.invoke(prompt)
        return {"synthesized_answer": response.content}
    except Exception as e:
        logger.error(f"Synthesizer failed: {e}")
        return {
            "synthesized_answer": "I'm sorry, I encountered an error while formulating the answer."
        }


def node_response_formatter_with_memory(state: AgentState) -> dict:
    logger.info("=== FORMATTER + MEMORY: Creating final response ===")
    sql_queries_str = "\n".join(
        [
            f"{'✓' if q['success'] else '✗'} {q['query_text']}"
            for q in state.get("executed_queries", [])
        ]
    )
    prompt = formatter_prompt.invoke(
        {
            "enhanced_query": state.get("enhanced_query", state["input"]),
            "synthesized_answer": state.get(
                "synthesized_answer", "No answer generated."
            ),
            "sql_queries": sql_queries_str or "No queries executed",
        }
    )
    try:
        result: FormatterOutput = formatter_llm.invoke(prompt)
        new_turn = ConversationTurn(
            query=state["input"],
            answer=result.final_answer,
            entities=result.entities_to_save,
            tables_used=state["selected_tables"],
            executed_queries=state["executed_queries"],
        )
        history = state.get("conversation_history", [])[-4:] + [new_turn]
        return {
            "final_answer": result.final_answer,
            "sql_summary": result.sql_summary,
            "conversation_history": history,
            "conversation_turn": state.get("conversation_turn", 0) + 1,
        }
    except Exception as e:
        logger.error(f"Formatter failed: {e}")
        return {"final_answer": state.get("synthesized_answer", "Error in formatting.")}


# =========================================================================
# --- CONDITIONAL EDGES (UPDATED) ---
# =========================================================================
def should_route_simple(state: AgentState) -> str:
    return "__end__" if state.get("final_answer") else "continue_to_schema_builder"


def should_run_planner(state: AgentState) -> str:
    return "run_planner" if state.get("needs_planning") else "skip_planner"


def should_continue_or_synthesize(state: AgentState) -> str:
    """FIXED: More robust check for when the agent is finished."""
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "continue_to_validator"
    if "proceeding to synthesis" in last_message.content.lower():
        return "continue_to_synthesis"
    # Default to synthesis if no tool calls are made and no explicit finish message
    return "continue_to_synthesis"


def did_validation_fail(state: AgentState) -> str:
    """NEW: Checks if the last message is a validation error to loop back."""
    if state["messages"] and isinstance(state["messages"][-1], ToolMessage):
        if "VALIDATION ERROR" in state["messages"][-1].content:
            logger.warning("Validation failed. Looping back to agent to retry.")
            return "retry_with_agent"
    logger.info("Validation passed. Proceeding to execute tool.")
    return "execute_tool"


# =========================================================================
# --- GRAPH DEFINITION (CORRECTED) ---
# =========================================================================
workflow = StateGraph(AgentState)

# Add all nodes
workflow.add_node("smart_router", node_smart_router)
workflow.add_node("schema_builder", node_schema_builder)
workflow.add_node("query_planner", node_query_planner)
workflow.add_node("react_agent", node_tool_calling_agent)
workflow.add_node("sql_validator", node_sql_validator)
workflow.add_node("tool_executor", node_tool_executor)
workflow.add_node("answer_synthesizer", node_answer_synthesizer)
workflow.add_node("response_formatter", node_response_formatter_with_memory)

# Set entry point
workflow.set_entry_point("smart_router")

# Define the logical flow
workflow.add_conditional_edges(
    "smart_router",
    should_route_simple,
    {"__end__": END, "continue_to_schema_builder": "schema_builder"},
)
workflow.add_conditional_edges(
    "schema_builder",
    should_run_planner,
    {"run_planner": "query_planner", "skip_planner": "react_agent"},
)
workflow.add_edge("query_planner", "react_agent")
workflow.add_conditional_edges(
    "react_agent",
    should_continue_or_synthesize,
    {
        "continue_to_validator": "sql_validator",
        "continue_to_synthesis": "answer_synthesizer",
    },
)
workflow.add_conditional_edges(
    "sql_validator",
    did_validation_fail,
    {"retry_with_agent": "react_agent", "execute_tool": "tool_executor"},
)
workflow.add_edge("tool_executor", "react_agent")
workflow.add_edge("answer_synthesizer", "response_formatter")
workflow.add_edge("response_formatter", END)

# Compile the graph
app = workflow.compile()

logger.info("=== Graph Builder V3 (FIXED) Loaded ===")
logger.info(
    "Fixes: 1. Corrected and simplified graph logic. 2. Added robust validation error handling loop."
)
