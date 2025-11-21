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

    # 2. Call the API
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        
        try:
            # Make HTTP request to the FastAPI backend
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    f"{API_BASE_URL}/chat",
                    json={
                        "query": prompt,
                        "thread_id": st.session_state.thread_id
                    }
                )
                response.raise_for_status()
                data = response.json()

                full_response = data["answer"]
                st.session_state.thread_id = data["thread_id"]

                message_placeholder.markdown(full_response)
            
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
