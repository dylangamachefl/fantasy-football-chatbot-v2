import os
import csv
import logging
import streamlit as st
from dotenv import load_dotenv
from typing import Any, List, Optional, Set, Dict
from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate
from langchain_community.utilities import SQLDatabase
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.callbacks.base import BaseCallbackHandler
from langchain.schema import AgentAction, AgentFinish
from langchain_community.tools.sql_database.tool import QuerySQLDatabaseTool

## Import ConversationBufferMemory for stateful chat history.
from langchain.memory import ConversationBufferMemory

# --- Page Configuration (MUST BE FIRST!) ---
st.set_page_config(page_title="Fantasy Football Oracle", page_icon="🏈")

# --- Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="agent_debug.log",
    filemode="w",
)
logger = logging.getLogger(__name__)


# --- Pydantic Model for Structured Output ---
class TableSelection(BaseModel):
    """Structured output format for table selection."""

    tables: List[str] = Field(
        description="List of table names needed to answer the query. Include ALL relevant tables."
    )
    reasoning: str = Field(
        description="Brief explanation of why these tables were selected"
    )


class LoggingCallbackHandler(BaseCallbackHandler):
    def on_chain_start(
        self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs: Any
    ) -> Any:
        """Log the inputs when a chain starts, with checks for None."""
        if serialized is None:
            return

        logger.info("=" * 80)
        chain_name = serialized.get("name", serialized.get("id", ["UnknownChain"])[-1])
        logger.info(f"CHAIN START: {chain_name}")
        logger.info("INPUTS:")

        for key, value in inputs.items():
            if key == "agent_scratchpad":
                logger.info(f"  - {key}: [present]")
                continue
            if key == "history" and len(str(value)) > 400:
                logger.info(f"  - {key}: [present, truncated]")
                continue
            logger.info(f"  - {key}:\n{value}")
        logger.info("=" * 80)

    def on_agent_action(self, action: AgentAction, **kwargs: Any) -> Any:
        logger.info(
            f"Agent Action: {action.tool} called with input:\n{action.tool_input}"
        )

    def on_tool_end(self, output: str, **kwargs: Any) -> Any:
        logger.info(f"Tool End: Tool produced output:\n{output}")

    def on_agent_finish(self, finish: AgentFinish, **kwargs: Any) -> Any:
        logger.info(f"Agent Finished: Final Answer:\n{finish.return_values['output']}")
        logger.info("=" * 80 + "\n")


load_dotenv()
if not os.getenv("GOOGLE_API_KEY"):
    raise ValueError("GOOGLE_API_KEY not found.")


@st.cache_resource
def get_llm():
    """Initializes and returns the LLM instance."""
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite",
        temperature=0,
    )


@st.cache_resource
def get_structured_llm():
    """Returns an LLM configured for structured output."""
    base_llm = get_llm()
    return base_llm.with_structured_output(TableSelection)


@st.cache_resource
def get_db():
    """Initializes and returns the database connection."""
    return SQLDatabase.from_uri(
        f"sqlite:///{'llm_fantasy_data.db'}",
        sample_rows_in_table_info=0,
        lazy_table_reflection=True,
        view_support=True,
    )


llm = get_llm()
structured_llm = get_structured_llm()
db = get_db()


@st.cache_data
def load_table_descriptions(filepath: str) -> str:
    """Load table descriptions from CSV file."""
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
        st.error(f"Failed to load table dictionary: {e}")
        logger.error(f"Failed to load table dictionary: {e}")
        return ""


@st.cache_data
def get_detailed_schema_info(
    table_names: List[str], filepath: str = "data_dictionary.csv"
) -> str:
    """
    Parses the data dictionary to get rich, human-readable column descriptions.
    Returns a well-formatted schema string for the agent.
    """
    logger.info(f"Loading schema for tables: {table_names}")

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
                logger.warning(
                    f"No schema found in {filepath} for {table_names}, using basic schema"
                )
                return db.get_table_info(table_names=table_names)

            logger.info(f"Found {len(relevant_rows)} column descriptions in {filepath}")

            # Group by table
            table_schemas = {}
            for row in relevant_rows:
                table_name = row["table_name"]
                if table_name not in table_schemas:
                    table_schemas[table_name] = []

                col_info = f"  • {row['column_name']}: {row['column_description']}"
                table_schemas[table_name].append(col_info)

            # Build clear, well-formatted schema string
            schema_parts = [
                "=" * 70,
                "DATABASE SCHEMA - AVAILABLE TABLES AND COLUMNS",
                "=" * 70,
                "",
                "These are the ONLY tables and columns you can use:",
                "",
            ]

            for table, columns in table_schemas.items():
                schema_parts.append(f"📊 Table: {table}")
                schema_parts.extend(columns)
                schema_parts.append("")

            schema_parts.append("=" * 70)
            schema_parts.append(
                "IMPORTANT: Do not reference any tables or columns not listed above."
            )
            schema_parts.append("=" * 70)

            full_schema = "\n".join(schema_parts)
            logger.info("Schema built successfully")
            return full_schema

    except FileNotFoundError:
        logger.error(f"Data dictionary file not found at {filepath}")
        return db.get_table_info(table_names=table_names)
    except Exception as e:
        logger.error(f"Error reading {filepath}: {e}", exc_info=True)
        return db.get_table_info(table_names=table_names)


def route_query(query: str) -> Optional[str]:
    """Handle simple queries that don't need database access."""
    query_words: Set[str] = set(query.lower().split())
    greetings: Set[str] = {"hello", "hi", "hey"}
    thanks: Set[str] = {"thanks", "thank"}

    if greetings.intersection(query_words):
        return "Hello! How can I help you with your fantasy league data?"
    if thanks.intersection(query_words):
        return "You're welcome!"
    return None


def get_relevant_tables_with_pydantic(
    user_query: str, history: str, table_descriptions: str
) -> tuple[List[str], str]:
    """
    Use LLM with structured output (Pydantic) to identify which tables are needed.
    Returns: (list of table names, reasoning)

    BENEFIT: Guaranteed correct format, no parsing errors!
    """
    prompt = f"""You are an expert database routing assistant. Identify ALL database tables required to answer the user's question.

**CRITICAL: If the question asks about PEOPLE or NAMES, you MUST include FantasyOwners_LLM**

**Mandatory Table Selection Rules (DO NOT VIOLATE THESE):**

1. **Questions about PEOPLE/WINNERS/NAMES (WHO questions):**
   - Keywords: "who", "winner", "champion", "owner", "name", "player"
   - **ALWAYS include:** FantasyOwners_LLM + FantasySeasons_LLM
   - Example: "Who won in 2017?" → [FantasySeasons_LLM, FantasyOwners_LLM]
   
2. **Questions about TEAMS:**
   - Keywords: "team", "team name"
   - **ALWAYS include:** FantasyTeams_LLM + related tables
   
3. **Questions about MATCHUPS/GAMES/SCORES:**
   - Keywords: "game", "matchup", "score", "versus", "against"
   - **ALWAYS include:** FantasyMatchups_LLM + related tables
   
4. **Questions about SEASONS/YEARS/CHAMPIONSHIPS:**
   - Keywords: "season", "year", "championship", numeric years (2017, 2020, etc.)
   - **ALWAYS include:** FantasySeasons_LLM
   - **IF asking WHO won:** Also include FantasyOwners_LLM

5. **When in doubt:**
   - Include MORE tables rather than fewer
   - Joining tables is cheap, missing data is expensive
   - If the question could POSSIBLY need owner names, include FantasyOwners_LLM

**Your Task:**
Analyze the user's question carefully:
- Look for keywords that indicate what information they want
- Think about what data you need to JOIN to get a complete answer
- Return ALL relevant table names (be generous, not conservative)

--- CONTEXT ---
Conversation History:
{history}

Available Tables:
{table_descriptions}

User Question: {user_query}
--- END CONTEXT ---

Remember: If the answer requires showing a PERSON'S NAME, you MUST include FantasyOwners_LLM!"""

    try:
        # This returns a TableSelection object with guaranteed structure
        result: TableSelection = structured_llm.invoke(prompt)

        # Post-processing safety check: If "who" or "winner" is in the query and FantasyOwners not selected, add it
        query_lower = user_query.lower()
        who_keywords = ["who", "winner", "champion", "owner"]

        if any(keyword in query_lower for keyword in who_keywords):
            if not any("fantasyowners" in table.lower() for table in result.tables):
                logger.warning(
                    f"Safety catch: Adding FantasyOwners_LLM for WHO question: {user_query}"
                )
                result.tables.append("FantasyOwners_LLM")
                result.reasoning += (
                    " [Safety: Added FantasyOwners_LLM for WHO question]"
                )

        logger.info(f"Table Selector (Pydantic) identified: {result.tables}")
        logger.info(f"Reasoning: {result.reasoning}")

        return result.tables, result.reasoning

    except Exception as e:
        logger.error(f"Structured table selector failed: {e}", exc_info=True)
        return [], "Error during table selection"


# --- Main Streamlit App ---
st.title("🏈 Fantasy Football Oracle")
st.write("Ask me anything about your league's history!")

# --- Sidebar Controls ---
with st.sidebar:
    st.header("⚙️ Controls")

    # Show conversation stats
    if "memory" in st.session_state:
        num_messages = len(st.session_state.memory.chat_memory.messages)
        st.metric("Messages in Context", num_messages)

    # Clear conversation button
    if st.button("🔄 Clear Conversation", use_container_width=True, type="primary"):
        st.session_state.memory = ConversationBufferMemory(
            memory_key="history",
            input_key="input",
            return_messages=True,
            max_token_limit=2000,
        )
        st.rerun()

    st.markdown("---")
    st.caption(
        "💡 **Tip:** Clear the conversation if the Oracle seems confused or has too much context."
    )

# Load static resources
table_descriptions = load_table_descriptions("table_dictionary.csv")

# Initialize conversation memory
if "memory" not in st.session_state:
    st.session_state.memory = ConversationBufferMemory(
        memory_key="history",
        input_key="input",
        return_messages=True,
        max_token_limit=2000,
    )

# Display chat history
for message in st.session_state.memory.chat_memory.messages:
    role = "user" if message.type == "human" else "assistant"
    with st.chat_message(role):
        st.markdown(message.content)

# Main interaction loop
if prompt := st.chat_input("Ask a question about your league..."):
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("The Oracle is thinking..."):
            assistant_response_content = ""

            # 1. Check for simple queries
            simple_response = route_query(prompt)

            if simple_response:
                assistant_response_content = simple_response
                st.markdown(assistant_response_content)
            else:
                # 2. Complex query - use agentic workflow with Pydantic
                history_str = st.session_state.memory.load_memory_variables({})[
                    "history"
                ]

                # Get relevant tables with structured output (NO PARSING NEEDED!)
                relevant_tables, reasoning = get_relevant_tables_with_pydantic(
                    prompt, history_str, table_descriptions
                )

                # Validation: Retry once if no tables selected
                if not relevant_tables:
                    logger.warning("No tables selected, retrying...")
                    retry_query = f"Which database tables are needed for: '{prompt}'?"
                    relevant_tables, reasoning = get_relevant_tables_with_pydantic(
                        retry_query, "", table_descriptions
                    )

                if not relevant_tables:
                    assistant_response_content = (
                        "I'm having trouble understanding which data you need. "
                        "Could you rephrase your question? For example:\n"
                        "- 'Who won the championship in 2020?'\n"
                        "- 'What was my record against Jake?'\n"
                        "- 'Show me the top scorers from last season'"
                    )
                    st.warning(assistant_response_content)
                else:
                    # Generate schema for selected tables
                    forced_schema = get_detailed_schema_info(
                        table_names=relevant_tables, filepath="data_dictionary.csv"
                    )

                    # Show debugging info (INCLUDING REASONING!)
                    with st.expander("🕵️ Agent's Internal Context"):
                        st.markdown("**Tables Selected:**")
                        st.write(relevant_tables)
                        st.markdown("**Selection Reasoning:**")
                        st.info(
                            reasoning
                        )  # THIS IS NEW - shows WHY tables were selected
                        st.markdown("---")
                        st.markdown("**Schema Provided to Agent:**")
                        st.code(forced_schema, language="text")

                    # Create and execute agent
                    agent_executor = create_specialized_agent(forced_schema)
                    logger.info(f"Invoking agent with tables: {relevant_tables}")

                    try:
                        logging_callback = LoggingCallbackHandler()
                        response = agent_executor.invoke(
                            {"input": prompt, "history": history_str},
                            config={"callbacks": [logging_callback]},
                        )
                        assistant_response_content = response["output"]
                        st.markdown(assistant_response_content)

                    except Exception as e:
                        error_str = str(e).lower()

                        if "no such column" in error_str:
                            error_message = (
                                "⚠️ I tried to query a column that doesn't exist."
                            )
                        elif "no such table" in error_str:
                            error_message = (
                                "⚠️ I tried to access a table that doesn't exist."
                            )
                        elif (
                            "timeout" in error_str or "max_execution_time" in error_str
                        ):
                            error_message = (
                                "⏱️ The query took too long. Try a simpler question."
                            )
                        else:
                            error_message = f"❌ Error: {e}"

                        st.error(error_message)
                        logger.error(f"Agent execution failed: {e}", exc_info=True)
                        assistant_response_content = (
                            "Sorry, I couldn't answer that question."
                        )

    # Save to memory
    st.session_state.memory.save_context(
        {"input": prompt}, {"output": assistant_response_content}
    )
