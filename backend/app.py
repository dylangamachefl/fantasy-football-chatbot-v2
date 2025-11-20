import streamlit as st
import uuid
import os
from dotenv import load_dotenv  # <--- ADD THIS

# 1. Load Environment Variables (API Keys & Tracing)
load_dotenv()

# 2. (Optional) Set a specific Project Name for the App
# This keeps your App traces separate from your Evaluation traces in LangSmith
os.environ["LANGCHAIN_PROJECT"] = "fantasy-football-chatbot-live"

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

# CRITICAL CHANGE: Import 'workflow', not 'app'.
# We need to compile the workflow with memory inside this script.
from graph_builder import workflow

st.set_page_config(page_title="Fantasy Football Chatbot", page_icon="🏈")
st.title("Fantasy Football Chatbot 🏈")

# =============================================================================
# 1. SESSION STATE SETUP
# =============================================================================

# Initialize the Chat History (for UI display)
if "messages" not in st.session_state:
    st.session_state.messages = []

# Initialize a Unique Thread ID (for LangGraph Memory)
# This ensures the bot remembers context for this specific user session.
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

# =============================================================================
# 2. GRAPH SETUP (With Memory)
# =============================================================================


# We use @st.cache_resource to compile the graph only ONCE per session.
# This prevents creating a new MemorySaver (and wiping memory) on every rerun.
@st.cache_resource
def get_graph_app():
    memory = MemorySaver()
    # Compile the graph with the checkpointer
    return workflow.compile(checkpointer=memory)


app = get_graph_app()
config = {"configurable": {"thread_id": st.session_state.thread_id}}

# =============================================================================
# 3. UI LOGIC
# =============================================================================

# Display prior chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Handle User Input
if prompt := st.chat_input("Ask me about fantasy football..."):

    # 1. Display User Message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. Invoke LangGraph
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):

            # Prepare the input
            # We ONLY pass the *new* message. The MemorySaver handles the history.
            # We also pass 'input' because the Router node expects it.
            input_dict = {"messages": [HumanMessage(content=prompt)], "input": prompt}

            # Run the graph with the config (Thread ID)
            final_state = app.invoke(input_dict, config=config)

            # Extract the Final Response
            # Because of our Responder node, the last message is always the final answer.
            assistant_response = final_state["messages"][-1].content

            # Display Response
            st.markdown(assistant_response)

            # Save to History
            st.session_state.messages.append(
                {"role": "assistant", "content": assistant_response}
            )

            # 3. Debug / Context Expander
            with st.expander("🕵️ Agent's Internal Context"):
                # Show Table Selection
                st.markdown("**Tables Selected:**")
                st.write(final_state.get("selected_tables"))

                # Show Router Reasoning
                st.markdown("**Router Reasoning:**")
                st.info(final_state.get("table_selection_reasoning"))

                # Show SQL Query (Trace the history to find the tool call)
                st.markdown("**SQL Generated:**")
                # Scan messages for the SQL tool call
                found_sql = False
                for msg in reversed(final_state["messages"]):
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        for tool in msg.tool_calls:
                            if tool["name"] == "sql_db_query":
                                st.code(tool["args"]["query"], language="sql")
                                found_sql = True
                                break
                    if found_sql:
                        break
