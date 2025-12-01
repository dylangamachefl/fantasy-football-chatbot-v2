# --- START OF FILE workflow.py ---

import logging
import re
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

# --- Import our agent state ---
from .state import AgentState

# --- Import helper functions and models from sql_agent.py ---
from .sql_agent import (
    get_db,
    load_table_descriptions,
    get_detailed_schema_info,
    VALID_FANTASY_OWNERS,
    SafeSQLQueryTool,
)

from .dspy_config import init_dspy
from .dspy_modules import get_query_enhancer, get_table_router, get_responder, get_sql_generator

# --- Setup ---
logger = logging.getLogger(__name__)
init_dspy()


# =========================================================================
# --- Graph Nodes ---
# =========================================================================
# --- graph_builder.py ---


# --- graph_builder.py ---

# Common greeting patterns (case-insensitive)
GREETING_PATTERNS = [
    "hi", "hello", "hey", "greetings", "howdy", "sup", "yo",
    "good morning", "good afternoon", "good evening",
    "what's up", "whats up", "how are you", "how's it going"
]

def is_greeting(text: str) -> bool:
    """Check if the input is a simple greeting."""
    text_lower = text.lower().strip().rstrip("!?.,")
    # Check for exact matches or very short greetings
    return text_lower in GREETING_PATTERNS or (len(text.split()) <= 3 and any(g in text_lower for g in GREETING_PATTERNS[:7]))

def node_greeting_handler(state: AgentState) -> dict:
    """
    Node 0: Greeting Handler.
    Responds to simple greetings without querying the database.
    """
    logger.info("---NODE: GREETING HANDLER---")
    
    response_text = """Hi there! 👋 I'm your Fantasy Football Oracle assistant. 
    
I can help you explore your league's history and stats. Try asking me things like:
- "Who won the championship in 2020?"
- "What's Dylan's all-time record?"
- "Show me the best draft picks from 2019"
- "How did Chris perform this season?"

What would you like to know?"""
    
    return {"messages": [AIMessage(content=response_text)]}

def should_handle_greeting(state: AgentState) -> str:
    """Routing function to decide if we should handle as greeting or continue to query processing."""
    user_input = state["input"]
    
    # Only treat as greeting if it's a simple greeting with no follow-up question
    if is_greeting(user_input):
        logger.info(f"Detected greeting: {user_input}")
        return "greeting"
    return "query"


def node_query_enhancer(state: AgentState) -> dict:
    """
    Node 0: The Context & Narrative Enhancer.
    Rewrites the user's question to ensure the final answer feels like a story, not a spreadsheet.
    Also resolves pronouns ("he", "it") using history to make the Router's job easier.
    """
    logger.info("---NODE: QUERY ENHANCER---")
    user_query = state["input"]

    # We need the history to resolve "he", "that year", etc.
    history = str(state["messages"]) # Convert history to string for DSPy

    try:
        query_enhancer = get_query_enhancer()
        result = query_enhancer(history=history, user_query=user_query)
        enhanced_query = result.enhanced_query
    except Exception as e:
        logger.error(f"Query Enhancer failed: {e}", exc_info=True)
        enhanced_query = user_query

    logger.info(f"Original: {user_query}")
    logger.info(f"Enhanced: {enhanced_query}")

    # Overwrite 'input' with the better version.
    # The Router and SQL Agent will now see the explicit, rich question.
    return {"input": enhanced_query}


def node_table_router(state: AgentState) -> dict:
    """
    Node 1: The Database Router.
    Uses Python to pre-validate Owner names to prevent LLM hallucinations.
    """
    logger.info("---NODE: TABLE ROUTER---")

    # Initialize resources lazily to avoid import-time errors
    structured_llm = get_structured_llm()
    table_descriptions = load_table_descriptions()

    user_query = state["input"]

    core_tables = {
        "FantasyOwners_LLM",
        "FantasySeasons_LLM",
        "FantasyTeams_LLM",
        "FantasyMatchups_LLM",
    }

    # --- PYTHON LOGIC START ---
    # We check for exact name matches before the LLM even sees the prompt.
    # We split by whitespace to ensure we match "Chris" but not "Christian"
    query_words = set(word.strip(",.?!").lower() for word in user_query.split())
    valid_owners_lower = {name.lower(): name for name in VALID_FANTASY_OWNERS}

    detected_owners = []
    for word in query_words:
        if word in valid_owners_lower:
            detected_owners.append(valid_owners_lower[word])

    # Build the "Hint" String
    owner_hint = ""
    if detected_owners:
        names_str = ", ".join(detected_owners)
        owner_hint = f"""
*** SYSTEM NOTIFICATION ***
The user mentioned: **{names_str}**.
These are VERIFIED FANTASY OWNERS in this league.
Rules for this query:
1. You MUST treat "{names_str}" as a specific League Member, NOT an NFL player.
2. Do NOT select `Players_LLM`.
***************************
"""
    # --- PYTHON LOGIC END ---

    try:
        table_router = get_table_router()
        # Ensure input args match the module signature
        # Signature: user_query, table_descriptions, hint
        result = table_router(
            user_query=user_query,
            table_descriptions=table_descriptions,
            hint=owner_hint
        )

        # Parse the output. DSPy output is a Prediction object, attributes match output fields.
        # selected_tables might be a string representation of a list if generated by LLM text.
        # However, dspy.OutputField is usually text.
        # We need to parse the list from text if it's not structured.
        # But wait, we can use dspy.TypedPredictor if we want structured output,
        # but here we used dspy.ChainOfThought(Signature).
        # We need to robustly parse the `selected_tables` field.

        raw_tables = result.selected_tables
        reasoning = result.reasoning

        # Simple cleanup if it's a string like "['TableA', 'TableB']"
        if isinstance(raw_tables, str):
            # Remove brackets and split
            cleaned = raw_tables.strip("[]").replace("'", "").replace('"', "")
            llm_selected = {t.strip() for t in cleaned.split(",")} if cleaned.strip() else set()
        elif isinstance(raw_tables, list):
            llm_selected = set(raw_tables)
        else:
            llm_selected = set()

        # Merge with Core
        final_tables = list(core_tables.union(llm_selected))

        logger.info(
            f"Tables selected: {final_tables} (Core: {core_tables} | LLM: {llm_selected})"
        )

        return {
            "selected_tables": final_tables,
            "table_selection_reasoning": reasoning,
        }

    except Exception as e:
        logger.error(f"Table router failed: {e}", exc_info=True)
        return {"selected_tables": list(core_tables)}


def node_schema_builder(state: AgentState) -> dict:
    """
    Node 2: Schema Builder.
    Retrieves the specific columns for the selected tables.
    """
    logger.info("---NODE: SCHEMA BUILDER---")
    if not state.get("selected_tables"):
        # If no tables selected, we can't build a schema.
        # The flow will continue, but the agent will likely fail or ask for clarification.
        return {"forced_schema": ""}

    schema = get_detailed_schema_info(table_names=state["selected_tables"])
    return {"forced_schema": schema}


def node_sql_agent(state: AgentState) -> dict:
    """
    Node 3: The Constrained SQL Agent (DSPy Powered).
    Generates SQL using DSPy and executes it.
    """
    logger.info("---NODE: SQL AGENT (DSPy)---")

    if not state.get("forced_schema"):
        return {"messages": [AIMessage(content="Error: No schema found.")]}

    schema = state["forced_schema"]
    # query_enhancer rewrites the input to be self-contained in state['input'].
    question = state["input"]

    sql_generator = get_sql_generator()

    # Try generation
    try:
        prediction = sql_generator(question=question, db_schema=schema)
        sql_query = prediction.sql_query
        thought = prediction.thought
    except Exception as e:
        logger.error(f"SQL Generation failed: {e}", exc_info=True)
        return {"messages": [AIMessage(content=f"Error generating SQL: {e}")]}

    # Clean SQL (remove markdown if present)
    clean_sql = sql_query.replace("```sql", "").replace("```", "").strip()

    # Execute
    db = get_db()
    tool = SafeSQLQueryTool(db=db)

    # We want to mimic the tool calling behavior so the Responder sees a ToolMessage
    # Create AIMessage with the thought and the "tool call" visualization
    ai_msg = AIMessage(content=f"**Thought:** {thought}\n\n**Generated SQL:**\n```sql\n{clean_sql}\n```")

    # Execute
    try:
        # We can call tool._run directly
        result_str = tool._run(clean_sql)
        tool_msg = ToolMessage(
            content=result_str,
            tool_call_id="dspy_sql_call",
            name="sql_db_query"
        )
    except Exception as e:
        tool_msg = ToolMessage(
            content=f"Error executing SQL: {e}",
            tool_call_id="dspy_sql_call_error",
            name="sql_db_query"
        )

    return {"messages": [ai_msg, tool_msg]}


def node_responder(state: AgentState) -> dict:
    """
    Node 4: The Responder (Synthesizer).
    Looks at the conversation history (User Query -> SQL -> Tool Output) and speaks to the user.
    """
    logger.info("---NODE: RESPONDER---")

    # Extract the last few messages to serve as history
    history = str(state["messages"][:-1]) # exclude the very last one if we want, or include all

    # We need to extract the "Data Context" specifically from the ToolMessage if present
    data_context = "No new data."
    messages = state["messages"]
    if messages and isinstance(messages[-1], ToolMessage):
        data_context = messages[-1].content
    elif len(messages) > 1 and isinstance(messages[-2], ToolMessage):
        data_context = messages[-2].content

    try:
        responder = get_responder()
        result = responder(history=history, data_context=data_context)
        answer = result.answer
    except Exception as e:
        logger.error(f"Responder failed: {e}", exc_info=True)
        answer = "I'm sorry, I encountered an error while formulating the response."

    return {"messages": [AIMessage(content=answer)]}


# =========================================================================
# --- Graph Definition ---
# =========================================================================
# --- graph_builder.py ---

# ... imports and nodes ...

workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("greeting_handler", node_greeting_handler)  # <--- NEW: Handles greetings
workflow.add_node("query_enhancer", node_query_enhancer)
workflow.add_node("table_router", node_table_router)
workflow.add_node("schema_builder", node_schema_builder)
workflow.add_node("sql_agent", node_sql_agent)
workflow.add_node("responder", node_responder)

# Define Edges
# Start with conditional routing: greeting vs. query
workflow.set_entry_point("query_enhancer")

# Add conditional edge from query_enhancer to either greeting handler or table router
workflow.add_conditional_edges(
    "query_enhancer",
    should_handle_greeting,
    {
        "greeting": "greeting_handler",
        "query": "table_router"
    }
)

# Greeting handler goes straight to END
workflow.add_edge("greeting_handler", END)

# Normal query flow continues as before
workflow.add_edge("table_router", "schema_builder")
workflow.add_edge("schema_builder", "sql_agent")
workflow.add_edge("sql_agent", "responder")
workflow.add_edge("responder", END)

app = workflow.compile()

logger.info("Fantasy Football Oracle Graph (Responder Pattern) compiled successfully.")

