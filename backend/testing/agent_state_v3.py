# --- agent_state_v3.py ---
# Updated state with schema_info key

from typing import List, Optional, TypedDict, Annotated, Dict
from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages


class ConversationTurn(TypedDict):
    """Represents one Q&A exchange in conversation history"""

    query: str
    answer: str
    entities: Dict[str, str]
    tables_used: List[str]
    executed_queries: List["QueryMetadata"]


class QueryMetadata(TypedDict):
    """Metadata about an executed SQL query"""

    query_text: str
    query_result: str
    execution_time_ms: float
    rows_returned: int
    tables_used: List[str]
    success: bool
    error_message: Optional[str]


class AgentState(TypedDict):
    """
    Enhanced state for our Fantasy Football agent with memory.
    """

    # ============================================================================
    # CORE MEMORY (unchanged)
    # ============================================================================
    messages: Annotated[list[BaseMessage], add_messages]

    # ============================================================================
    # INPUT & ENHANCED QUERY (unchanged)
    # ============================================================================
    input: str  # Raw user query
    enhanced_query: Optional[str]  # Query with resolved context

    # ============================================================================
    # CONVERSATION MEMORY (unchanged from v3)
    # ============================================================================
    conversation_history: Optional[List[ConversationTurn]]
    current_context: Optional[Dict[str, str]]
    conversation_turn: int

    # ============================================================================
    # SMART ROUTER OUTPUT (unchanged)
    # ============================================================================
    query_type: Optional[str]
    needs_planning: Optional[bool]
    complexity_score: Optional[int]
    selected_tables: Optional[List[str]]
    table_selection_reasoning: Optional[str]

    # ============================================================================
    # SCHEMA & PLANNING (Updated)
    # ============================================================================
    schema_info: Optional[str]  # <-- NEW: Stores the detailed schema
    query_plan: Optional[str]
    plan_steps: Optional[List[str]]

    # ============================================================================
    # SQL EXECUTION TRACKING (unchanged from v3)
    # ============================================================================
    executed_queries: Optional[List[QueryMetadata]]
    validation_errors: Optional[List[str]]

    # ============================================================================
    # ITERATION TRACKING (unchanged)
    # ============================================================================
    iteration_count: int

    # ============================================================================
    # OUTPUT (unchanged from v3)
    # ============================================================================
    synthesized_answer: Optional[str]
    final_answer: Optional[str]
    sql_summary: Optional[str]
    simple_response: Optional[str]
    entities_to_save: Optional[Dict[str, str]]


# Default values for fields
def create_initial_state(user_input: str) -> AgentState:
    """Helper to create initial state with defaults"""
    return AgentState(
        # Required
        messages=[],
        input=user_input,
        # Memory
        conversation_history=[],
        current_context={},
        conversation_turn=1,
        # Counters
        iteration_count=0,
        # Optional fields
        enhanced_query=None,
        query_type=None,
        needs_planning=None,
        complexity_score=None,
        selected_tables=None,
        table_selection_reasoning=None,
        schema_info=None,  # <-- NEW
        query_plan=None,
        plan_steps=None,
        executed_queries=[],
        validation_errors=[],
        synthesized_answer=None,
        final_answer=None,
        sql_summary=None,
        simple_response=None,
        entities_to_save=None,
    )
