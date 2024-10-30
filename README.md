# i-Shell

A Streamlit-based web wrapper based on this [repo](https://github.com/disler/anthropic-computer-use-bash-and-files/blob/main/src/anthropic_computer_use/main.py) that provides an AI-powered CLI assistant. This tool helps users execute and understand command-line operations through natural language interaction.

## Features

- Natural language processing of CLI commands
- Conversation history tracking
- Documentation upload support (PDF, TXT, MD)
- Dry run mode for command verification
- Automatic session management

## Prerequisites

- Python 3.8 or higher
- pip (Python package installer)

## Installation

1. Clone the repository:
```bash
git clone git@github.com:alexwohletz/cli_to_llm.git
cd cli_to_llm
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Linux/Mac
# OR
.\venv\Scripts\activate  # On Windows
```

3. Install the required packages:
```bash
pip install -r requirements.txt
```

## Environment Setup

Create a `.env` file in the project root directory with the following variables:
```
ANTHROPIC_API_KEY=your_api_key_here
```

You'll need an API key from Anthropic to use the Claude AI model. Visit [Anthropic's website](https://www.anthropic.com/) to obtain one.

## Running the Application

Start the Streamlit application:
```bash
streamlit run main.py
```

The application will open in your default web browser at `http://localhost:8501`.

## Usage

1. Type CLI commands or questions in natural language in the chat input
2. Upload relevant documentation files (PDF, TXT, MD) for context
3. Toggle "Dry Run Mode" in settings to verify commands without execution
4. View conversation history in the sidebar
5. Start new conversations or clear chat as needed

## Project Structure

- `main.py`: Main Streamlit application
- `cli_wrapper.py`: CLI interaction handling
- `requirements.txt`: Project dependencies
- `conversation_history/`: Stores chat histories
- `sessions/`: Manages CLI session data
- `uploads/`: Temporary storage for uploaded documentation

## Note

The application automatically creates necessary directories for conversation history, sessions, and uploads during runtime.
