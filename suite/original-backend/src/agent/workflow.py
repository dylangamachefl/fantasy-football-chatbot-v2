from langgraph.graph import StateGraph, START, END
from src.agent.state import AgentState
from src.agent.sql_agent import (
    node_greeting_handler,
    node_query_enhancer,
    node_table_router,
    node_schema_builder,
    node_sql_generator,
    node_sql_executor,
    node_responder,
)

def should_handle_greeting(state: AgentState):
    """
    Check if the user input is a simple greeting.
    """
    # Simple heuristic: if the input is short and contains greeting words
    # This logic was present in the original implementation implicitly or explicitly.
    # Since I don't have the original code logic, I'll implement a reasonable heuristic.
    text = state["raw_input"].lower().strip()
    greetings = {"hi", "hello", "hey", "greetings", "sup"}
    if text in greetings:
        return "greeting"
    # Also check if it's very short and just a greeting
    if len(text.split()) < 3 and any(g in text for g in greetings):
        return "greeting"
    return "continue"

def conditional_edge_check_result(state: AgentState):
    """
    Determines the next step based on the execution result.
    """
    error = state.get("error")
    retry_count = state.get("retry_count", 0)

    if error:
        if retry_count < 3:
            return "retry"
        else:
            return "error_abort"
    else:
        return "success"

# Define the graph
workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("greeting_handler", node_greeting_handler)
workflow.add_node("query_enhancer", node_query_enhancer)
workflow.add_node("table_router", node_table_router)
workflow.add_node("schema_builder", node_schema_builder)
workflow.add_node("sql_generator", node_sql_generator)
workflow.add_node("sql_executor", node_sql_executor)
workflow.add_node("responder", node_responder)

# Add Edges & Conditional Edges
# Start -> Check Greeting
workflow.add_conditional_edges(
    START,
    should_handle_greeting,
    {
        "greeting": "greeting_handler",
        "continue": "query_enhancer"
    }
)

workflow.add_edge("greeting_handler", END)

workflow.add_edge("query_enhancer", "table_router")
workflow.add_edge("table_router", "schema_builder")
workflow.add_edge("schema_builder", "sql_generator")
workflow.add_edge("sql_generator", "sql_executor")

# Conditional Edge for Retry
workflow.add_conditional_edges(
    "sql_executor",
    conditional_edge_check_result,
    {
        "retry": "sql_generator",
        "error_abort": "responder",
        "success": "responder",
    }
)

workflow.add_edge("responder", END)

# Compile the graph
app = workflow.compile()
