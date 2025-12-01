import streamlit as st
import uuid
import httpx
import json
import pandas as pd

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
    st.markdown("### 🏆 League Info")
    st.info("League founded in 2012.\n12 Teams.\nPPR Scoring.")

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
# HELPER: FEEDBACK
# =============================================================================
def submit_feedback(feedback_type, user_input, assistant_response, feedback_key):
    try:
        with httpx.Client() as client:
            client.post(
                f"{API_BASE_URL}/feedback",
                json={
                    "thread_id": st.session_state.thread_id,
                    "user_input": user_input,
                    "assistant_response": assistant_response,
                    "feedback_type": feedback_type
                }
            )
        st.session_state.feedback[feedback_key] = feedback_type
    except Exception as e:
        st.error(f"Failed to submit feedback: {e}")

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
        # 1. Text Content
        st.markdown(message["content"])
        
        # 2. Structured Data (Tables)
        if "data" in message:
            try:
                df = pd.DataFrame(message["data"]["data"])
                st.dataframe(df, use_container_width=True)
            except Exception:
                pass # Ignore if data is malformed

        # 3. SQL Debug
        if st.session_state.show_debug and "sql" in message:
             st.code(message["sql"], language="sql")

        # 4. Feedback
        if message["role"] == "assistant":
            # Use thread_id + index to make unique keys that survive "Clear Chat" if the state persists improperly
            # But "Clear Chat" resets st.session_state.messages, so idx resets too.
            # To be truly safe, we combine thread_id.
            unique_id = f"{st.session_state.thread_id}_{idx}"
            feedback_key = f"feedback_{unique_id}"
            
            # Initialize feedback state if not exists
            if "feedback" not in st.session_state:
                st.session_state.feedback = {}
            
            col1, col2, col3 = st.columns([0.1, 0.1, 0.8])
            
            # Determine if buttons should be disabled (already voted)
            is_voted = feedback_key in st.session_state.feedback

            with col1:
                if st.button("👍", key=f"thumbs_up_{unique_id}", disabled=is_voted):
                    # We need the user input that triggered this. It's usually the previous message.
                    user_input = st.session_state.messages[idx-1]["content"] if idx > 0 else ""
                    submit_feedback("positive", user_input, message["content"], feedback_key)
                    st.rerun()
            
            with col2:
                if st.button("👎", key=f"thumbs_down_{unique_id}", disabled=is_voted):
                    user_input = st.session_state.messages[idx-1]["content"] if idx > 0 else ""
                    submit_feedback("negative", user_input, message["content"], feedback_key)
                    st.rerun()
            
            # Show feedback status
            if is_voted:
                with col3:
                    feedback_type = st.session_state.feedback[feedback_key]
                    emoji = "✅" if feedback_type == "positive" else "❌"
                    st.caption(f"{emoji} Feedback recorded")


# Handle pending question from suggested questions
user_input = st.chat_input("Ask me about fantasy football...")

if "pending_question" in st.session_state:
    prompt = st.session_state.pending_question
    del st.session_state.pending_question
else:
    prompt = user_input

# Handle User Input
if prompt:
    # 1. Display User Message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. Call the API (Streaming)
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        # Temporary storage for this turn
        current_sql = None
        current_data = None

        try:
            # Make HTTP request to the FastAPI backend with streaming
            with httpx.Client(timeout=60.0) as client:
                with client.stream(
                    "POST",
                    f"{API_BASE_URL}/chat",
                    json={
                        "query": prompt,
                        "thread_id": st.session_state.thread_id
                    }
                ) as response:
                    response.raise_for_status()

                    # SSE Parsing Logic
                    event_type = None

                    for line in response.iter_lines():
                        line = line.strip()
                        if not line:
                            continue

                        if line.startswith("event:"):
                            event_type = line.split(":", 1)[1].strip()
                        elif line.startswith("data:"):
                            data_payload = line.split(":", 1)[1].strip()

                            if data_payload == "[DONE]":
                                break

                            try:
                                parsed = json.loads(data_payload)

                                if event_type == "meta":
                                    st.session_state.thread_id = parsed.get("thread_id", st.session_state.thread_id)

                                elif event_type == "token":
                                    full_response += parsed
                                    message_placeholder.markdown(full_response + "▌")

                                elif event_type == "sql":
                                    current_sql = parsed
                                    if st.session_state.show_debug:
                                        with st.expander("🔌 SQL Query Executed", expanded=True):
                                            st.code(current_sql, language="sql")

                                elif event_type == "data":
                                    # parsed is {"columns": [...], "data": [...]}
                                    current_data = parsed
                                    with st.expander("📊 Data Result", expanded=True):
                                        # Handle potential error strings being passed as data
                                        if isinstance(parsed, dict) and "data" in parsed:
                                            df = pd.DataFrame(parsed["data"])
                                            st.dataframe(df)
                                        else:
                                            # Fallback if data is not in expected format
                                            st.write(parsed)

                                elif event_type == "error":
                                    st.error(f"Backend Error: {parsed}")
                                    full_response = f"Error: {parsed}"

                            except json.JSONDecodeError:
                                pass

            # Finalize the UI
            message_placeholder.markdown(full_response)
            
            # Save to History
            msg_obj = {
                "role": "assistant",
                "content": full_response
            }
            if current_sql:
                msg_obj["sql"] = current_sql
            if current_data:
                msg_obj["data"] = current_data

            st.session_state.messages.append(msg_obj)

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
