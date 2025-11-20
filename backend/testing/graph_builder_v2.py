# --- graph_builder_v2.py ---
# Optimized agent with Strategies 1-4 implemented
# 3-5 LLM calls per query (down from 4-6)

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
from agent_state_v2 import AgentState, QueryMetadata, ConversationTurn

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# =========================================================================
# --- PYDANTIC MODELS ---
# =========================================================================


class SmartRouterOutput(BaseModel):
    """
    STRATEGY 1: Consolidated output from Smart Router
    Replaces: Router + Memory Manager + Query Enhancer + Table Selector
    """

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
    """Output from the conditional planner"""

    strategy: str = Field(description="High-level approach to answer the query")
    steps: List[str] = Field(description="Ordered steps to execute")
    estimated_queries: int = Field(description="Expected number of SQL queries")


class FormatterOutput(BaseModel):
    """
    STRATEGY 4: Consolidated output from Formatter + Memory
    """

    final_answer: str = Field(description="Natural language answer for user")
    sql_summary: str = Field(description="Summary of SQL queries executed")
    entities_to_save: Dict[str, str] = Field(
        description="Key entities to remember for next turn", default_factory=dict
    )


# =========================================================================
# --- HELPER FUNCTIONS (from original) ---
# =========================================================================


def get_llm():
    return ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0)


def get_structured_llm_router():
    """LLM for Smart Router with structured output"""
    return get_llm().with_structured_output(SmartRouterOutput)


def get_structured_llm_planner():
    """LLM for Planner with structured output"""
    return get_llm().with_structured_output(QueryPlan)


def get_structured_llm_formatter():
    """LLM for Formatter with structured output"""
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
    """Load detailed schema for selected tables (unchanged)"""
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
# --- STRATEGY 2: RULE-BASED SQL VALIDATOR ---
# =========================================================================


def validate_sql_query(
    query: str, allowed_tables: List[str], schema_info: str
) -> tuple[bool, Optional[str]]:
    """
    STRATEGY 2: Rule-based SQL validation (NO LLM CALL)

    Returns: (is_valid, error_message)
    """

    # 1. Check for dangerous keywords
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

    # 2. Parse SQL syntax
    try:
        parsed = sqlparse.parse(query)
        if not parsed:
            return False, "Could not parse SQL query"
    except Exception as e:
        return False, f"SQL syntax error: {str(e)}"

    # 3. Extract table names from query
    query_lower = query.lower()
    used_tables = []
    for table in allowed_tables:
        # Check if table name appears in query (basic check)
        if table.lower() in query_lower:
            used_tables.append(table)

    # 4. Verify tables exist in allowed list
    # Extract FROM and JOIN clauses
    from_tables = re.findall(r"from\s+(\w+)", query_lower)
    join_tables = re.findall(r"join\s+(\w+)", query_lower)
    referenced_tables = set(from_tables + join_tables)

    allowed_tables_lower = [t.lower() for t in allowed_tables]
    for table in referenced_tables:
        if table not in allowed_tables_lower:
            return (
                False,
                f"Table '{table}' not in selected tables. Available: {allowed_tables}",
            )

    # 5. Check complexity (basic heuristic)
    join_count = query_upper.count("JOIN")
    if join_count > 4:
        return (
            False,
            f"Query too complex ({join_count} JOINs). Simplify or break into multiple queries.",
        )

    # 6. Validate query has necessary components
    if "SELECT" not in query_upper:
        return False, "Query must be a SELECT statement"

    return True, None


# =========================================================================
# --- STRATEGY 3: COMPLEXITY SCORING (for conditional planning) ---
# =========================================================================


def calculate_complexity_score(query: str, num_tables: int) -> int:
    """
    STRATEGY 3: Rule-based complexity scoring (NO LLM CALL)

    Returns: Score from 1-10
    """
    score = 0
    query_lower = query.lower()

    # Factor 1: Number of tables
    score += num_tables

    # Factor 2: Comparison keywords
    comparison_keywords = ["compare", "versus", "vs", "difference", "between"]
    if any(kw in query_lower for kw in comparison_keywords):
        score += 2

    # Factor 3: Temporal complexity
    temporal_keywords = [
        "trend",
        "over time",
        "across seasons",
        "all seasons",
        "every year",
    ]
    if any(kw in query_lower for kw in temporal_keywords):
        score += 2

    # Factor 4: Aggregation complexity
    agg_keywords = ["average", "total", "sum", "count", "maximum", "minimum"]
    agg_count = sum(1 for kw in agg_keywords if kw in query_lower)
    score += min(agg_count, 2)

    # Factor 5: Multiple questions
    if "?" in query:
        score += query.count("?") - 1  # First question is baseline

    return min(score, 10)  # Cap at 10


# =========================================================================
# --- AGENT INITIALIZATION ---
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
# --- AGENT PROMPTS ---
# =========================================================================

# STRATEGY 1: Smart Router prompt (consolidates 4 nodes)
smart_router_prompt = f"""You are an intelligent query analyzer for a fantasy football database assistant.

**YOUR TASK:**
Analyze the user's query along with conversation history and determine:
1. Query type (greeting, simple query, complex query, or follow-up)
2. Enhance the query by resolving pronouns and adding context
3. Select required database tables
4. Assess complexity and planning needs
5. Extract key entities mentioned

**CONVERSATION CONTEXT:**
{{conversation_history}}

**CURRENT CONTEXT (entities being discussed):**
{{current_context}}

**AVAILABLE TABLES:**
{table_descriptions}

**USER'S QUERY:**
{{user_query}}

**CRITICAL RULES:**
1. **Resolve Pronouns**: Replace "he", "she", "it", "they", "him", "her" with actual names from context
2. **Resolve Time References**: Replace "last year", "this season", "then" with actual years/seasons from context
3. **Table Selection Rules (DO NOT VIOLATE):**
   - Questions about PEOPLE/WINNERS/NAMES (WHO): Include FantasyOwners_LLM + FantasySeasons_LLM
   - Questions about TEAMS: Include FantasyTeams_LLM
   - Questions about MATCHUPS/GAMES/SCORES: Include FantasyMatchups_LLM
   - Questions about SEASONS/YEARS: Include FantasySeasons_LLM
4. **Planning Needed**: Set needs_planning=True if query requires multiple steps, comparisons, or complex aggregations
5. **Greetings**: Set query_type="greeting" and provide quick_response for "hi", "hello", "thanks"

**OUTPUT:**
Provide structured analysis following the SmartRouterOutput schema.
"""

# Planner prompt (used conditionally)
planner_prompt = """You are a query planning expert for SQL databases.

Given a complex query, create a high-level strategy to answer it efficiently.

**QUERY:** {enhanced_query}

**AVAILABLE TABLES:** {selected_tables}

**TASK:**
Break down the approach into clear steps. Do NOT write SQL - just describe the strategy.

Example:
Query: "Compare championship winners' average regular season scores"
Strategy: "First get all championship winners, then aggregate their regular season scores, then compare"
Steps:
1. Query FantasySeasons_LLM for all champion_owner_id values
2. Join with FantasyOwners_LLM to get owner names
3. Query FantasyMatchups_LLM for their regular season games (is_a_playoff_matchup=0)
4. Calculate average scores per owner
5. Compare and rank

Provide similar structured plan for this query.
"""

# ReAct agent prompt (largely unchanged, now plan-aware)
system_prompt_string = """You are an expert SQLite data analyst. Your job is to answer questions by writing and executing SQL queries.

**CRITICAL RULES:**
1. This is SQLite - use ONLY SQLite syntax
2. **CRITICAL:** Only use tables and columns explicitly listed in the schema provided
3. **CRITICAL:** DO NOT invent table names. If you need standings/rankings, calculate from available tables
4. If a query fails, read the error message and fix it

{{query_plan}}

**YOUR GOAL:**
Answer the user's question by calling the `sql_db_query` tool to get data.

**PROBLEM-SOLVING:**
1. Call the tool to get data
2. Observe the output
3. **If output contains the answer:** Stop and provide answer in your response content
4. **If output is an error or empty:** Try a different approach

**COMMON PATTERNS:**
- **SCORES/MATCHUPS/RECORDS:** All in `FantasyMatchups_LLM` table
  - Regular season: `WHERE is_a_playoff_matchup = 0`
  - Playoffs: `WHERE is_a_playoff_matchup = 1`
- **CHAMPIONS:** In `FantasySeasons_LLM` table
- **OWNER NAMES:** Join `FantasyOwners_LLM` on `owner_id`

**WHEN YOU HAVE THE ANSWER:**
Just state the answer clearly in your content field. The formatter will make it natural.
"""

agent_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system_prompt_string),
        ("system", "DATABASE SCHEMA:\n{schema}"),
        MessagesPlaceholder(variable_name="messages"),
    ]
)

agent_chain = agent_prompt | llm_with_tools

# STRATEGY 4: Formatter + Memory prompt (consolidates 2 operations)
formatter_prompt = """You are a response formatter for a fantasy football assistant.

**TASK:** Create a natural language answer AND extract entities for conversation memory.

**USER'S ORIGINAL QUESTION:** {original_query}

**DATA WE FOUND:** {data}

**SQL QUERIES EXECUTED:**
{sql_queries}

**REQUIREMENTS:**
1. **Final Answer**: Write a clear, natural language response
2. **SQL Summary**: Briefly describe what queries were run (1-2 sentences)
3. **Entities to Save**: Extract key entities mentioned for next turn
   - Include: person names, seasons, teams, metrics discussed
   - Example: {{"person": "Steve", "season": "2023", "metric": "championships"}}

**STYLE:**
- Conversational and friendly
- Include the SQL summary so users can see what was queried
- If multiple queries were run, mention that
- Keep it concise but informative

Provide structured output following FormatterOutput schema.
"""


# =========================================================================
# --- NODE 1: SMART ROUTER/PREPROCESSOR (Strategy 1) ---
# =========================================================================


def node_smart_router(state: AgentState) -> dict:
    """
    STRATEGY 1: Consolidated router that replaces:
    - Original router
    - Memory manager
    - Query enhancer
    - Table selector

    Single LLM call handles all 4 tasks.
    """
    logger.info("=== SMART ROUTER: Starting ===")

    # Prepare conversation history string
    history_str = ""
    if state.get("conversation_history"):
        history_str = "Previous conversation:\n"
        for turn in state["conversation_history"][-3:]:  # Last 3 turns
            history_str += f"Q: {turn['query']}\nA: {turn['answer']}\n"

    # Prepare current context
    context_str = ""
    if state.get("current_context"):
        context_str = ", ".join(
            [f"{k}: {v}" for k, v in state["current_context"].items()]
        )

    # Build the comprehensive prompt
    prompt = smart_router_prompt.format(
        conversation_history=history_str or "No previous conversation",
        current_context=context_str or "No current context",
        user_query=state["input"],
    )

    try:
        # Single LLM call that does everything
        result: SmartRouterOutput = router_llm.invoke(prompt)

        logger.info(f"Query Type: {result.query_type}")
        logger.info(f"Enhanced Query: {result.enhanced_query}")
        logger.info(f"Selected Tables: {result.selected_tables}")
        logger.info(f"Needs Planning: {result.needs_planning}")
        logger.info(f"Complexity: {result.complexity_score}")

        # Calculate complexity score (rule-based check)
        complexity = calculate_complexity_score(
            result.enhanced_query, len(result.selected_tables)
        )

        # Update state with all outputs
        updates = {
            "query_type": result.query_type,
            "enhanced_query": result.enhanced_query,
            "selected_tables": result.selected_tables,
            "table_selection_reasoning": result.reasoning,
            "needs_planning": result.needs_planning
            or complexity > 6,  # Override if complex
            "complexity_score": max(complexity, result.complexity_score),
            "current_context": {**state.get("current_context", {}), **result.entities},
        }

        # Handle greetings
        if result.query_type == "greeting" and result.quick_response:
            updates["simple_response"] = result.quick_response
            updates["final_answer"] = result.quick_response
        else:
            # Add enhanced query to messages for the agent
            updates["messages"] = [HumanMessage(content=result.enhanced_query)]

        return updates

    except Exception as e:
        logger.error(f"Smart Router failed: {e}")
        # Fallback: treat as simple query
        return {
            "query_type": "simple_query",
            "enhanced_query": state["input"],
            "selected_tables": [],
            "needs_planning": False,
            "messages": [HumanMessage(content=state["input"])],
        }


# =========================================================================
# --- NODE 2: SCHEMA BUILDER (unchanged) ---
# =========================================================================


def node_schema_builder(state: AgentState) -> dict:
    """Load detailed schema for selected tables (unchanged from original)"""
    logger.info("=== SCHEMA BUILDER: Loading schema ===")

    forced_schema = get_detailed_schema_info(table_names=state["selected_tables"])
    schema_message = SystemMessage(content=f"DATABASE SCHEMA:\n{forced_schema}")

    return {"messages": [schema_message] + state["messages"]}


# =========================================================================
# --- NODE 3: CONDITIONAL PLANNER (Strategy 3) ---
# =========================================================================


def node_query_planner(state: AgentState) -> dict:
    """
    STRATEGY 3: Only runs for complex queries
    Creates high-level strategy (not detailed SQL)
    """
    logger.info("=== QUERY PLANNER: Creating strategy ===")

    prompt = planner_prompt.format(
        enhanced_query=state["enhanced_query"], selected_tables=state["selected_tables"]
    )

    try:
        plan: QueryPlan = planner_llm.invoke(prompt)

        logger.info(f"Strategy: {plan.strategy}")
        logger.info(f"Steps: {plan.steps}")

        return {"query_plan": plan.strategy, "plan_steps": plan.steps}
    except Exception as e:
        logger.error(f"Planning failed: {e}")
        return {"query_plan": "Direct query approach"}


# =========================================================================
# --- NODE 4: REACT AGENT (mostly unchanged, now plan-aware) ---
# =========================================================================


def node_tool_calling_agent(state: AgentState) -> dict:
    """
    ReAct agent - thinks and decides on tool calls
    Now receives optional query plan as guidance
    """
    logger.info(f"=== REACT AGENT: Iteration {state['iteration_count']} ===")

    # Circuit breaker
    if state["iteration_count"] >= 10:
        logger.warning("Max iterations reached!")
        return {
            "messages": [AIMessage(content="Query too complex. Please simplify.")],
            "final_answer": "I apologize, but this query is too complex. Could you break it into simpler questions?",
        }

    # Build schema
    forced_schema = get_detailed_schema_info(table_names=state["selected_tables"])

    # Add plan context if available
    plan_context = ""
    if state.get("query_plan"):
        plan_context = f"\n\n**SUGGESTED STRATEGY:**\n{state['query_plan']}\n"
        if state.get("plan_steps"):
            plan_context += "Steps:\n" + "\n".join(
                [f"{i+1}. {step}" for i, step in enumerate(state["plan_steps"])]
            )

    # Invoke agent
    llm_response = agent_chain.invoke(
        {
            "schema": forced_schema,
            "query_plan": plan_context,
            "messages": state["messages"],
        }
    )

    return {"messages": [llm_response], "iteration_count": state["iteration_count"] + 1}


# =========================================================================
# --- NODE 5: SQL VALIDATOR (Strategy 2) ---
# =========================================================================


def node_sql_validator(state: AgentState) -> dict:
    """
    STRATEGY 2: Rule-based SQL validation (NO LLM CALL)
    Checks syntax, schema, and safety before execution
    """
    logger.info("=== SQL VALIDATOR: Checking queries ===")

    last_message = state["messages"][-1]

    # Only validate if there are tool calls
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {}  # Nothing to validate

    schema_info = get_detailed_schema_info(table_names=state["selected_tables"])
    validation_errors = []

    for tool_call in last_message.tool_calls:
        if tool_call["name"] == "sql_db_query":
            query = tool_call["args"].get("query", "")

            # Rule-based validation
            is_valid, error = validate_sql_query(
                query, state["selected_tables"], schema_info
            )

            if not is_valid:
                validation_errors.append(
                    f"Query validation failed: {error}\nQuery: {query}"
                )
                logger.warning(f"Validation error: {error}")

    if validation_errors:
        # Add validation errors to state
        all_errors = state.get("validation_errors", []) + validation_errors

        # Create a feedback message for the agent
        error_message = ToolMessage(
            content=f"VALIDATION ERROR: {validation_errors[0]}\nPlease revise your query.",
            tool_call_id=last_message.tool_calls[0]["id"],
        )

        return {"validation_errors": all_errors, "messages": [error_message]}

    # Validation passed
    return {}


# =========================================================================
# --- NODE 6: TOOL EXECUTOR (updated to capture metadata) ---
# =========================================================================


def node_tool_executor(state: AgentState) -> dict:
    """
    Execute SQL queries and capture metadata for observability
    """
    logger.info("=== TOOL EXECUTOR: Running queries ===")

    last_message = state["messages"][-1]

    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {}

    tool_messages = []
    query_metadata = state.get("executed_queries", [])

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_input = tool_call["args"]

        if tool_name not in tool_map:
            tool_messages.append(
                ToolMessage(
                    content=f"Error: Tool '{tool_name}' not found.",
                    tool_call_id=tool_call["id"],
                )
            )
            continue

        try:
            import time

            start_time = time.time()

            # Execute the tool
            tool_output = tool_map[tool_name].invoke(tool_input)

            execution_time = (time.time() - start_time) * 1000  # Convert to ms

            # Count rows (basic heuristic)
            rows_returned = str(tool_output).count("\n") if tool_output else 0

            # Capture metadata
            metadata = QueryMetadata(
                query_text=tool_input.get("query", ""),
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

            logger.info(
                f"Query executed in {execution_time:.2f}ms, {rows_returned} rows"
            )

        except Exception as e:
            # Capture error metadata
            metadata = QueryMetadata(
                query_text=tool_input.get("query", ""),
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
            logger.error(f"Tool execution error: {e}")

    return {"messages": tool_messages, "executed_queries": query_metadata}


# =========================================================================
# --- NODE 7: FORMATTER + MEMORY (Strategy 4) ---
# =========================================================================


def node_response_formatter_with_memory(state: AgentState) -> dict:
    """
    STRATEGY 4: Consolidated formatter that:
    1. Formats the final answer
    2. Summarizes SQL queries
    3. Extracts entities for memory

    Single LLM call handles all 3 tasks.
    """
    logger.info("=== FORMATTER + MEMORY: Creating final response ===")

    # Get the final data from the agent
    final_data = str(state["messages"][-1].content)

    # Build SQL summary
    sql_queries_str = ""
    if state.get("executed_queries"):
        sql_queries_str = "Executed queries:\n"
        for i, q in enumerate(state["executed_queries"], 1):
            status = "✓" if q["success"] else "✗"
            sql_queries_str += f"{i}. {status} {q['query_text'][:100]}...\n"
            sql_queries_str += (
                f"   Time: {q['execution_time_ms']:.2f}ms, Rows: {q['rows_returned']}\n"
            )

    prompt = formatter_prompt.format(
        original_query=state["input"],
        data=final_data,
        sql_queries=sql_queries_str or "No queries executed",
    )

    try:
        result: FormatterOutput = formatter_llm.invoke(prompt)

        logger.info(f"Final answer: {result.final_answer[:100]}...")
        logger.info(f"Entities saved: {result.entities_to_save}")

        # Create conversation turn for memory
        new_turn = ConversationTurn(
            query=state["input"],
            answer=result.final_answer,
            entities=result.entities_to_save,
            tables_used=state["selected_tables"],
        )

        # Update conversation history (keep last 5 turns)
        history = state.get("conversation_history", [])
        history.append(new_turn)
        if len(history) > 5:
            history = history[-5:]

        return {
            "final_answer": result.final_answer,
            "sql_summary": result.sql_summary,
            "entities_to_save": result.entities_to_save,
            "conversation_history": history,
            "conversation_turn": state.get("conversation_turn", 0) + 1,
        }

    except Exception as e:
        logger.error(f"Formatter failed: {e}")
        # Fallback: simple formatting
        return {
            "final_answer": f"Based on the data: {final_data}",
            "sql_summary": f"Executed {len(state.get('executed_queries', []))} queries",
        }


# =========================================================================
# --- CONDITIONAL EDGES ---
# =========================================================================


def should_route_simple(state: AgentState) -> str:
    """After Smart Router: is this a greeting?"""
    if state.get("simple_response"):
        return "__end__"
    return "continue_to_schema_builder"


def should_run_planner(state: AgentState) -> str:
    """STRATEGY 3: Only run planner if needed"""
    if state.get("needs_planning"):
        logger.info("Complex query detected - running planner")
        return "run_planner"
    logger.info("Simple query - skipping planner")
    return "skip_planner"


def should_continue_or_format(state: AgentState) -> str:
    """After validator: continue loop or exit?"""

    # Check if validator rejected the query
    if state.get("validation_errors"):
        recent_errors = state["validation_errors"]
        # If we just added errors, those will be in messages as ToolMessage
        # So we continue to let agent try again
        return "continue_to_tools"

    last_message = state["messages"][-1]

    # If agent wants to call tools, go to validator
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "continue_to_validator"

    # Agent is done - format the response
    return "continue_to_formatter"


# =========================================================================
# --- GRAPH DEFINITION ---
# =========================================================================

workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("smart_router", node_smart_router)
workflow.add_node("schema_builder", node_schema_builder)
workflow.add_node("query_planner", node_query_planner)
workflow.add_node("react_agent", node_tool_calling_agent)
workflow.add_node("sql_validator", node_sql_validator)
workflow.add_node("tool_executor", node_tool_executor)
workflow.add_node("response_formatter", node_response_formatter_with_memory)

# Set entry point
workflow.set_entry_point("smart_router")

# Edges
workflow.add_conditional_edges(
    "smart_router",
    should_route_simple,
    {"__end__": END, "continue_to_schema_builder": "schema_builder"},
)

workflow.add_edge("schema_builder", "react_agent")

# Conditional planner
workflow.add_conditional_edges(
    "react_agent",
    should_continue_or_format,
    {
        "continue_to_validator": "sql_validator",
        "continue_to_formatter": "response_formatter",
    },
)

# Validator can either pass to executor or loop back
workflow.add_edge("sql_validator", "tool_executor")
workflow.add_edge("tool_executor", "react_agent")  # Loop back

workflow.add_edge("response_formatter", END)

# Compile
app = workflow.compile()

# Save diagram
try:
    app.get_graph().draw_mermaid_png(output_file_path="graph_v2_optimized.png")
    logger.info("Graph diagram saved as graph_v2_optimized.png")
except Exception as e:
    logger.warning(f"Could not draw graph: {e}")

logger.info("=== Graph Builder V2 Loaded ===")
logger.info("Optimizations: Strategies 1-4 implemented")
logger.info("Expected LLM calls: 3-5 per query")
