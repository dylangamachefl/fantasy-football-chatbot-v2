# --- agent_state_v2.py ---
# Updated state with memory and conversation tracking

from typing import List, Optional, TypedDict, Annotated, Dict
from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages


class ConversationTurn(TypedDict):
    """Represents one Q&A exchange in conversation history"""

    query: str
    answer: str
    entities: Dict[str, str]  # e.g., {"person": "Steve", "season": "2023"}
    tables_used: List[str]


class QueryMetadata(TypedDict):
    """Metadata about an executed SQL query"""

    query_text: str
    execution_time_ms: float
    rows_returned: int
    tables_used: List[str]
    success: bool
    error_message: Optional[str]


class AgentState(TypedDict):
    """
    Enhanced state for our Fantasy Football agent with memory.

    NEW in v2:
    - Conversation history for multi-turn support
    - Current context for entity tracking
    - Query metadata for SQL visibility
    - Enhanced query with resolved context
    """

    # ============================================================================
    # CORE MEMORY (unchanged)
    # ============================================================================
    messages: Annotated[list[BaseMessage], add_messages]

    # ============================================================================
    # INPUT & ENHANCED QUERY (updated for Strategy 1)
    # ============================================================================
    input: str  # Raw user query
    enhanced_query: Optional[str]  # Query with pronouns resolved, context added

    # ============================================================================
    # CONVERSATION MEMORY (new - for multi-turn conversations)
    # ============================================================================
    conversation_history: Optional[List[ConversationTurn]]  # Last N turns
    current_context: Optional[Dict[str, str]]  # Currently discussed entities
    # Example: {"person": "Steve", "season": "2023", "metric": "championships"}

    conversation_turn: int  # Which turn in the conversation (for tracking)

    # ============================================================================
    # SMART ROUTER OUTPUT (Strategy 1 - consolidated from multiple nodes)
    # ============================================================================
    query_type: Optional[
        str
    ]  # "greeting" | "simple_query" | "complex_query" | "follow_up"
    needs_planning: Optional[bool]  # Does this require the planner node?
    complexity_score: Optional[int]  # 1-10 scale for query complexity

    # ============================================================================
    # TABLE SELECTION (moved to Smart Router output)
    # ============================================================================
    selected_tables: Optional[List[str]]
    table_selection_reasoning: Optional[str]

    # ============================================================================
    # PLANNING (Strategy 3 - conditional)
    # ============================================================================
    query_plan: Optional[str]  # High-level strategy if planning was done
    plan_steps: Optional[List[str]]  # Ordered list of steps to execute

    # ============================================================================
    # SQL EXECUTION TRACKING (for observability)
    # ============================================================================
    executed_queries: Optional[List[QueryMetadata]]  # All SQL queries run
    validation_errors: Optional[List[str]]  # Any validation issues encountered

    # ============================================================================
    # ITERATION TRACKING (safety)
    # ============================================================================
    iteration_count: int  # Number of ReAct loops (circuit breaker)

    # ============================================================================
    # OUTPUT (updated for Strategy 4)
    # ============================================================================
    final_answer: Optional[str]
    sql_summary: Optional[str]  # Summary of SQL queries for user
    simple_response: Optional[str]  # For greetings

    # Entities to remember for next turn (extracted during formatting)
    entities_to_save: Optional[Dict[str, str]]


# Default values for fields
def create_initial_state(user_input: str) -> AgentState:
    """Helper to create initial state with defaults"""
    return AgentState(
        # Required
        messages=[],
        input=user_input,
        # Memory (start empty)
        conversation_history=[],
        current_context={},
        conversation_turn=1,
        # Counters
        iteration_count=0,
        # Optional fields start as None
        enhanced_query=None,
        query_type=None,
        needs_planning=None,
        complexity_score=None,
        selected_tables=None,
        table_selection_reasoning=None,
        query_plan=None,
        plan_steps=None,
        executed_queries=[],
        validation_errors=[],
        final_answer=None,
        sql_summary=None,
        simple_response=None,
        entities_to_save=None,
    )
