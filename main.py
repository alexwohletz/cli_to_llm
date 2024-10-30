import streamlit as st
from typing import List, Dict, Any
import os
from datetime import datetime
import uuid
import json
from cli_wrapper import BashSession, SessionLogger, SESSIONS_DIR
import time
from pypdf import PdfReader
from pathlib import Path
import shutil

# Directory to store conversation history and uploads
HISTORY_DIR = os.path.join(os.getcwd(), "conversation_history")
UPLOADS_DIR = os.path.join(os.getcwd(), "uploads")
os.makedirs(HISTORY_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

def load_conversation_history(conversation_id: str) -> List[Dict[str, str]]:
    """Load conversation history from file."""
    history_file = os.path.join(HISTORY_DIR, f"{conversation_id}.json")
    if os.path.exists(history_file):
        with open(history_file, 'r') as f:
            return json.load(f)
    return []

def save_conversation_history(conversation_id: str, history: List[Dict[str, str]]):
    """Save conversation history to file."""
    # Add timestamp if not present in the first message
    if history and 'timestamp' not in history[0]:
        history[0]['timestamp'] = datetime.now().isoformat()
        
    history_file = os.path.join(HISTORY_DIR, f"{conversation_id}.json")
    with open(history_file, 'w') as f:
        json.dump(history, f)

def get_conversation_list() -> List[tuple[str, List[Dict[str, str]]]]:
    """Get list of all conversations with their first message, sorted by creation time."""
    conversations = []
    for filename in os.listdir(HISTORY_DIR):
        if filename.endswith('.json'):
            conv_id = filename[:-5]  # Remove .json
            history = load_conversation_history(conv_id)
            if history:  # Only include non-empty conversations
                first_msg = history[0]["content"] if history else "Empty conversation"
                # Get timestamp or use file creation time as fallback
                timestamp = history[0].get('timestamp', datetime.fromtimestamp(
                    os.path.getctime(os.path.join(HISTORY_DIR, filename))
                ).isoformat())
                conversations.append((conv_id, first_msg, timestamp))
    
    # Sort conversations by timestamp in descending order (newest first)
    conversations.sort(key=lambda x: x[2], reverse=True)
    # Return without the timestamp in the result to maintain compatibility
    return [(conv_id, msg) for conv_id, msg, _ in conversations]

def save_uploaded_file(uploaded_file) -> str:
    """Save uploaded file and return its path."""
    file_path = os.path.join(UPLOADS_DIR, uploaded_file.name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path

def get_uploaded_docs() -> List[str]:
    """Get list of uploaded documentation files."""
    if not os.path.exists(UPLOADS_DIR):
        return []
    return [f for f in os.listdir(UPLOADS_DIR) if os.path.isfile(os.path.join(UPLOADS_DIR, f))]

def load_doc_content(filename: str) -> str:
    """Load content of an uploaded documentation file."""
    file_path = os.path.join(UPLOADS_DIR, filename)
    file_path = Path(file_path)

    if file_path.suffix == ".pdf":
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
    if file_path.suffix in [".txt", ".md"]:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    
def clear_uploads_directory():
    """Clear all files from the uploads directory."""
    if os.path.exists(UPLOADS_DIR):
        shutil.rmtree(UPLOADS_DIR)
    os.makedirs(UPLOADS_DIR, exist_ok=True)

def init_session(dry_mode: bool = False) -> tuple[BashSession, SessionLogger, str]:
    """Initialize a new bash session and logger."""
    session_id = f"{datetime.now().strftime('%Y%m%d-%H:%M:%S-%f')}"
    bash_session = BashSession(session_id=session_id, no_agi=dry_mode)
    session_logger = SessionLogger(session_id, SESSIONS_DIR)
    bash_session.set_logger(session_logger)
    conversation_id = str(uuid.uuid4())
    # Clear uploads directory when starting a new session
    clear_uploads_directory()
    return bash_session, session_logger, conversation_id

def process_bot_response(message: str, history: List[Dict[str, str]], state: tuple) -> str:
    """Process the bot's response and handle streaming."""
    bash_session, session_logger, _ = state
    
    # Add documentation context if available
    docs_context = ""
    if 'uploaded_docs' in st.session_state:
        for doc in st.session_state.uploaded_docs:
            docs_context += f"\nReference documentation from {doc}:\n{load_doc_content(doc)}\n"
    
    if docs_context:
        message = f"Using the following documentation as reference:\n{docs_context}\n\nUser query: {message}"
    
    # Process the message through BashSession with full conversation history
    bash_session.process_bash_command(message, history)
    
    # Get the assistant's response and any tool calls
    response_text = ""
    for msg in reversed(bash_session.messages):
        if msg["role"] == "assistant":
            for content in msg["content"]:
                if content["type"] == "text":
                    response_text = content["text"]
                    break
            break
    
    # Add tool calls to the response if any were made
    if bash_session.current_tool_calls:
        tool_calls_text = "\n\n🔧 Commands executed:\n"
        for tool_call in bash_session.current_tool_calls:
            tool_calls_text += f"```bash\n{tool_call['command']}\n```\n"
        response_text = tool_calls_text + "\n" + response_text
    
    return response_text

def main():
    st.set_page_config(
        page_title="ClaudeShell",
        page_icon="🤖",
        layout="wide"
    )
    
    # Initialize session states
    if 'dark_mode' not in st.session_state:
        st.session_state.dark_mode = False
    if 'uploaded_docs' not in st.session_state:
        st.session_state.uploaded_docs = []  # Initialize as empty list instead of loading existing files
    if 'history' not in st.session_state:
        st.session_state.history = []
    if 'session_info' not in st.session_state:
        st.session_state.session_info = init_session(st.session_state.get('dry_mode', False))
        conversation_id = st.session_state.session_info[2]
        st.session_state.history = load_conversation_history(conversation_id)
    
    # Sidebar
    with st.sidebar:
        st.title("Settings")
        dry_toggle = st.toggle("Dry Run Mode", key="dry_mode", value=False)
        st.title("Conversation History")
        if st.button("New Chat"):
            st.session_state.history = []
            st.session_state.uploaded_docs = []  # Clear uploaded docs list
            st.session_state.session_info = init_session(dry_toggle)
            save_conversation_history(st.session_state.session_info[2], [])
            st.rerun()
        
        for conv_id, first_msg in get_conversation_list():
            if st.button(f"{first_msg[:50]}...", key=conv_id):
                st.session_state.history = load_conversation_history(conv_id)
                st.session_state.uploaded_docs = []  # Clear uploaded docs list
                st.session_state.session_info = init_session(dry_toggle)
                st.session_state.session_info = (
                    st.session_state.session_info[0],
                    st.session_state.session_info[1],
                    conv_id
                )
                st.rerun()

    # Main chat area
    st.title("🤖 Cli Assistant")
    st.markdown("""
    Chat with an AI assistant that can understand a CLI instantly and help you with simple to complex tasks.
    Your conversation history is automatically saved.
    """)

    # Example commands
    with st.expander("Example Commands"):
        example_commands = [
            "List files in the current directory that end with '.py'",
            "Setup a new python virtual environment named 'env' and install requirements.txt if available",
            "Show system information",
            "Setup git"
        ]
        for cmd in example_commands:
            if st.button(cmd):
                # Process the example command directly
                st.session_state.history.append({"role": "user", "content": cmd})
                response = process_bot_response(cmd, st.session_state.history, st.session_state.session_info)
                st.session_state.history.append({"role": "assistant", "content": response})
                save_conversation_history(st.session_state.session_info[2], st.session_state.history)
                st.rerun()

    # Chat container
    chat_container = st.container()
    
    with chat_container:
        if not st.session_state.history:
            with st.chat_message("assistant"):
                st.write("👋 Hello! I'm your CLI assistant. How can I help you today?")
        
        for message in st.session_state.history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    # Input area with buttons
    col1, col2, col3 = st.columns([6,1,1])
    
    # Chat input
    with col1:
        if prompt := st.chat_input("Type your command here..."):
            st.session_state.history.append({"role": "user", "content": prompt})
            response = process_bot_response(prompt, st.session_state.history, st.session_state.session_info)
            st.session_state.history.append({"role": "assistant", "content": response})
            save_conversation_history(st.session_state.session_info[2], st.session_state.history)
            st.rerun()
        uploaded_file = st.file_uploader('Upload CLI documentation to the chat',type=['txt', 'md', 'pdf'], label_visibility="visible")
        if uploaded_file:
            if uploaded_file.name not in st.session_state.uploaded_docs:
                save_uploaded_file(uploaded_file)
                st.session_state.uploaded_docs.append(uploaded_file.name)
                st.rerun()
        if st.button("Clear Chat"):
            st.session_state.history = []
            st.session_state.uploaded_docs = []  # Clear uploaded docs list
            st.session_state.session_info = init_session(dry_toggle)
            save_conversation_history(st.session_state.session_info[2], [])
            st.rerun()

if __name__ == "__main__":
    main()
