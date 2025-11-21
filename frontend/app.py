import streamlit as st
import uuid
import httpx
import json

# API Configuration
API_BASE_URL = "http://localhost:8000"

st.set_page_config(page_title="Fantasy Football Chatbot", page_icon="🏈", layout="wide")

# =============================================================================
# SIDEBAR
# =============================================================================
with st.sidebar:
    st.title("⚙️ Settings")
    
    # Clear Chat Button
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.thread_id = str(uuid.uuid4())
        st.rerun()
    
    # Debug Mode Toggle
    if "show_debug" not in st.session_state:
        st.session_state.show_debug = False
    
    st.session_state.show_debug = st.checkbox("🐛 Show Debug Info", value=st.session_state.show_debug)
    
    st.divider()
    st.caption("Fantasy Football Oracle v2.0")

# =============================================================================
# SESSION STATE SETUP
# =============================================================================

# Initialize the Chat History (for UI display)
if "messages" not in st.session_state:
    st.session_state.messages = []

# Initialize a Unique Thread ID (for API conversation persistence)
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

# =============================================================================
# MAIN UI
# =============================================================================

st.title("Fantasy Football Chatbot 🏈")

# Suggested Questions
st.markdown("### 💡 Try asking:")
col1, col2, col3 = st.columns(3)

suggested_questions = [
    "🏆 Who won the 2020 championship?",
    "📊 Show me Dylan's all-time record",
    "🔥 Who's the all-time leading scorer?"
]

for idx, (col, question) in enumerate(zip([col1, col2, col3], suggested_questions)):
    with col:
        if st.button(question, key=f"suggest_{idx}", use_container_width=True):
            # Remove emoji from the actual query
            clean_question = question.split(" ", 1)[1]
            st.session_state.pending_question = clean_question

st.divider()

# Display prior chat messages
for idx, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        
        # Add feedback buttons for assistant messages
        if message["role"] == "assistant":
            feedback_key = f"feedback_{idx}"
            
            # Initialize feedback state if not exists
            if "feedback" not in st.session_state:
                st.session_state.feedback = {}
            
            col1, col2, col3 = st.columns([0.1, 0.1, 0.8])
            
            with col1:
                if st.button("👍", key=f"thumbs_up_{idx}"):
                    st.session_state.feedback[feedback_key] = "positive"
                    st.rerun()
            
            with col2:
                if st.button("👎", key=f"thumbs_down_{idx}"):
                    st.session_state.feedback[feedback_key] = "negative"
                    st.rerun()
            
            # Show feedback status
            if feedback_key in st.session_state.feedback:
                with col3:
                    feedback_type = st.session_state.feedback[feedback_key]
                    emoji = "✅" if feedback_type == "positive" else "❌"
                    st.caption(f"{emoji} Feedback recorded")


# Handle pending question from suggested questions
if "pending_question" in st.session_state:
    prompt = st.session_state.pending_question
    del st.session_state.pending_question
else:
    prompt = st.chat_input("Ask me about fantasy football...")

# Handle User Input
if prompt:
    # 1. Display User Message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. Call the Streaming API
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        data_placeholder = st.empty()  # For SQL data visualization
        full_response = ""
        sql_data = None
        
        try:
            # Make streaming HTTP request to the FastAPI backend
            with httpx.Client(timeout=60.0) as client:
                with client.stream(
                    "POST",
                    f"{API_BASE_URL}/chat/stream",
                    json={
                        "query": prompt,
                        "thread_id": st.session_state.thread_id
                    }
                ) as response:
                    response.raise_for_status()
                    
                    # Process Server-Sent Events
                    for line in response.iter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]  # Remove "data: " prefix
                            try:
                                data = json.loads(data_str)
                                event_type = data.get("type")
                                
                                if event_type == "thread_id":
                                    # Update thread_id
                                    st.session_state.thread_id = data["thread_id"]
                                    if st.session_state.show_debug:
                                        st.caption(f"🔗 Thread ID: {data['thread_id']}")
                                
                                elif event_type == "token":
                                    # Accumulate streaming tokens
                                    full_response += data["content"]
                                    message_placeholder.markdown(full_response + "▌")
                                
                                elif event_type == "content":
                                    # Full content (fallback if no streaming)
                                    full_response = data["content"]
                                    message_placeholder.markdown(full_response)
                                
                                elif event_type == "sql_data":
                                    # SQL data for visualization
                                    sql_data = data
                                    if st.session_state.show_debug:
                                        st.caption(f"📊 SQL Query: `{data.get('query', 'N/A')}`")
                                
                                elif event_type == "done":
                                    # Remove cursor and finalize
                                    message_placeholder.markdown(full_response)
                                    
                                    # Display SQL data if available
                                    if sql_data:
                                        with data_placeholder.container():
                                            st.markdown("---")
                                            st.markdown("**📊 Data:**")
                                            
                                            # Convert to DataFrame for better display
                                            import pandas as pd
                                            data_rows = sql_data.get("data", [])
                                            
                                            if data_rows and isinstance(data_rows, list):
                                                # Create DataFrame
                                                if isinstance(data_rows[0], (list, tuple)):
                                                    df = pd.DataFrame(data_rows)
                                                    st.dataframe(df, use_container_width=True)
                                                else:
                                                    # Single column result
                                                    df = pd.DataFrame(data_rows, columns=["Value"])
                                                    st.dataframe(df, use_container_width=True)
                                
                                elif event_type == "error":
                                    error_msg = f"⚠️ Error: {data['error']}"
                                    message_placeholder.error(error_msg)
                                    full_response = error_msg
                                    
                            except json.JSONDecodeError:
                                continue
            
            # Save to History
            st.session_state.messages.append(
                {"role": "assistant", "content": full_response}
            )

        except httpx.ConnectError:
            error_msg = "⚠️ Cannot connect to the API. Please make sure the FastAPI backend is running on http://localhost:8000"
            message_placeholder.error(error_msg)
            st.session_state.messages.append(
                {"role": "assistant", "content": error_msg}
            )
        except httpx.HTTPStatusError as e:
            error_msg = f"⚠️ API Error: {e.response.status_code} - {e.response.text}"
            message_placeholder.error(error_msg)
            st.session_state.messages.append(
                {"role": "assistant", "content": error_msg}
            )
        except Exception as e:
            error_msg = f"⚠️ Unexpected error: {str(e)}"
            message_placeholder.error(error_msg)
            st.session_state.messages.append(
                {"role": "assistant", "content": error_msg}
            )
