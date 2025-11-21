# --- START OF FILE state.py ---

from typing import List, Optional, TypedDict, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages


class AgentState(TypedDict):
    """
    Defines the state for our simplified, two-stage agent.
    """

    # The running conversation history
    messages: Annotated[list, add_messages]

    # The raw user input
    input: str

    # The list of tables selected by the router node
    selected_tables: Optional[List[str]]

    # The reasoning provided by the router node for its selection
    table_selection_reasoning: Optional[str]

    # The detailed, filtered schema provided to the SQL agent
    forced_schema: Optional[str]

    # A simple counter to prevent infinite loops
    iteration_count: int
