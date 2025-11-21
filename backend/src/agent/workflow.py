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
    get_llm,
    get_structured_llm,
    load_table_descriptions,
    get_detailed_schema_info,
    build_sql_agent_graph,
    TableSelection,
    VALID_FANTASY_OWNERS,
)

# --- Setup ---
logger = logging.getLogger(__name__)


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
    history = state["messages"]

    llm = get_llm()

    system_prompt = """You are a helpful assistant that refines user questions for a Fantasy Football database.
    
    Your goal is to rewrite the user's question to be **Specific** and **Narratively Rich**.
    
    **RULES FOR REWRITING:**
    1. **Resolve Pronouns (CRITICAL):** 
       - If the user says "he", "him", "his team", or "that year", replace it with the specific Name or Year from the conversation history.
       - *Ex:* "Did he make the playoffs?" -> "Did Dylan make the playoffs in 2021?"
       
    2. **Add Narrative Context (Not just stats):**
       - If asking **"Who won?"**: Rewrite to "Who won the championship, who was the runner-up, and what was the score?" (Stories need a winner AND a loser).
       - If asking **"Who had the best record?"**: Rewrite to "Who had the best record and what was their specific Win-Loss count?"
       - If asking **"Did X beat Y?"**: Rewrite to "Did X beat Y and what was the score difference?"
       
    3. **Keep it Natural:** 
       - Do not ask for "columns". Ask for "details".
       - If the user is just chatting ("Hi", "Thanks"), return the input unchanged.

    **OUTPUT:**
    Return ONLY the rewritten question.
    """

    # We pass the system prompt + the last few messages of context + the current input
    # This allows the LLM to see "Who won in 2016?" (History) -> "Jack" (History) -> "Who did he play?" (Current)
    # And rewrite it to: "Who did Jack play in the 2016 championship?"
    messages = [SystemMessage(content=system_prompt)] + history

    response = llm.invoke(messages)
    enhanced_query = response.content

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

    prompt = f"""You are an expert database architect. Identify the database tables required.

{owner_hint}

**CONTEXTUAL ANALYSIS (CRITICAL):**
1. **Follow-up Questions:** When the user sends a message, you MUST look at the **Conversation History** to understand the topic. If they are following up on a previous question about Owners, Drafts, or Matchups, you MUST include those relevant Specialty Tables.
2. **New Topics:** If the user changes the subject completely, ignore the old tables and select based on the new question.

**TABLE SELECTION INSTRUCTIONS:**
- Your job is to select **Specialty Tables** needed *in addition* to the Core Tables.
- **Core Tables (Auto-Included):** `FantasyOwners_LLM`, `FantasySeasons_LLM`, `FantasyTeams_LLM`, 'FantasyMatchups_LLM'.
- **If the User's question can be answered using ONLY the Core Tables (e.g., "How many points did Chris score?", "Who won in 2020?"), return an EMPTY list `[]`.**
- If the user asks about Matchups, Drafts, or Players, select those specific tables.
- Its better to include extra tables that might be helpful than to miss a needed one.

**NAME DISAMBIGUATION RULES:**
1. **Single First Name** (e.g. "Chris", "Dylan") -> **Owner**. (Use Core Tables).
2. **Full Name / Nickname** (e.g. "Chris Godwin", "CMC") -> **NFL Player**. (Use `Players_LLM`).

**"CHEAT SHEET" TABLES:**
- **All-Time Records:** `OwnerCareerLeaderboard_LLM`.
- **Regular Season Records:** `RegularSeasonStandings_LLM`.
- **Head-to-Head:** `HeadToHeadMatchups_LLM`.
- **Drafts:** `DraftAnalysis_Full_LLM`.

**PLAYER STATS LOGIC:**
- Only select `Players_LLM` if the name is **NOT** a valid Owner.
- If asking about an NFL Player, include `Players_LLM` + all Position tables for the timeframe.

**Available Tables:**
{table_descriptions}

**User Question:**
"{user_query}"

Return the list of table names (or empty list if only Core Tables are needed).
"""

    try:
        result: TableSelection = structured_llm.invoke(prompt)
        llm_selected = set(result.tables)

        # Merge with Core
        final_tables = list(core_tables.union(llm_selected))

        logger.info(
            f"Tables selected: {final_tables} (Core: {core_tables} | LLM: {llm_selected})"
        )

        return {
            "selected_tables": final_tables,
            "table_selection_reasoning": result.reasoning,
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
    Node 3: The Constrained SQL Agent.
    Includes a "Safety Net" for when the agent writes SQL but forgets to call the tool.
    """
    logger.info("---NODE: SQL AGENT---")

    if not state.get("forced_schema"):
        return {"messages": [AIMessage(content="Error: No schema found.")]}

    # 1. Run the Subgraph
    agent_graph = build_sql_agent_graph(forced_schema=state["forced_schema"])
    result = agent_graph.invoke({"messages": state["messages"]})

    # 2. Get the New Messages
    new_messages = result["messages"][len(state["messages"]) :]

    # 3. LOGGING (Keep your trace logic)
    print("\n" + "=" * 40)
    print("🤖 AGENT INTERNAL THOUGHTS:")
    for msg in new_messages:
        if isinstance(msg, AIMessage) and msg.content:
            print(f"\n{str(msg.content).strip()}\n")
    print("=" * 40 + "\n")

    # -------------------------------------------------------
    # THE SAFETY NET: Catch "Code Block Hallucination"
    # -------------------------------------------------------
    if new_messages:
        last_msg = new_messages[-1]

        # Check if the agent acted (Tool Call) or just talked (AIMessage)
        if isinstance(last_msg, AIMessage) and not last_msg.tool_calls:

            # Regex to find SQL inside markdown blocks ```sql ... ```
            sql_match = re.search(
                r"```sql\n(.*?)\n```", str(last_msg.content), re.DOTALL
            )

            if sql_match:
                logger.info(
                    "Agent wrote SQL but forgot to call tool. Executing manually..."
                )
                sql_query = sql_match.group(1).strip()

                try:
                    # Manually run the query
                    db = get_db()
                    tool_result = db.run(sql_query)

                    # Inject the result as a ToolMessage so the Responder sees it
                    # We make up a dummy tool_call_id
                    manual_tool_msg = ToolMessage(
                        content=tool_result,
                        tool_call_id="manual_safety_net_fix",
                        name="sql_db_query",
                    )
                    new_messages.append(manual_tool_msg)

                except Exception as e:
                    # If the manual run fails, pass the error to the responder
                    new_messages.append(
                        ToolMessage(
                            content=f"Error executing SQL: {e}",
                            tool_call_id="manual_safety_net_error",
                            name="sql_db_query",
                        )
                    )
            else:
                # Standard cleanup: If no SQL found and no tool call, strip the message
                # (unless you want to keep the agent's apology/confusion)
                new_messages.pop()

    # -------------------------------------------------------

    return {"messages": new_messages}


def node_responder(state: AgentState) -> dict:
    """
    Node 4: The Responder (Synthesizer).
    Looks at the conversation history (User Query -> SQL -> Tool Output) and speaks to the user.
    """
    logger.info("---NODE: RESPONDER---")

    llm = get_llm()

    # 1. System Instructions
    system_prompt = """You are a helpful fantasy football assistant.
Your job is to look at the recent database results in the conversation history and answer the user's question.

RULES:
1. Answer the user's LATEST question using the LATEST database results.
2. **Ignore older Tool Outputs** from previous turns in the conversation history. Only focus on the data returned in the most recent step.
3. If a SQL query was run and returned data (it will be a JSON string with "columns" and "data"), use that data to answer naturally.
4. If the database returned empty/no data, tell the user you couldn't find that information.
5. Do NOT mention "SQL", "Tuples", "Python", or "Database columns". Just give the answer.
"""

    # 2. The "Poke"
    # Gemini often stops processing after seeing a ToolMessage.
    # We inject a final HumanMessage to force it to evaluate the tool output and generate a response.
    force_response_message = HumanMessage(
        content="Based on the database results above, please answer my original question."
    )

    # 3. Construct the Input
    # System Prompt + Full History + The Poke
    messages = (
        [SystemMessage(content=system_prompt)]
        + state["messages"]
        + [force_response_message]
    )

    # 4. Generate Answer
    response = llm.invoke(messages)

    return {"messages": [response]}


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

