import os
import anthropic
import subprocess
from datetime import datetime   
from typing import Dict, Any, List, Optional
import traceback
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

# Source: https://github.com/disler/anthropic-computer-use-bash-and-files/blob/main/src/anthropic_computer_use/main.py

EDITOR_DIR = os.path.join(os.getcwd(), "editor_dir")
SESSIONS_DIR = os.path.join(os.getcwd(), "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)
load_dotenv()

# Fetch system prompts from environment variables or use defaults
BASH_SYSTEM_PROMPT = os.environ.get(
    "BASH_SYSTEM_PROMPT",
    """You are a helpful assistant that can execute bash commands and assist with running command-line tooling.
    When running in dry run mode, you should explain what commands you would execute and their expected effects,
    but note that they won't actually be run. Format your dry run explanations clearly, starting with "🔍 Dry Run:"
    followed by the explanation of what would happen if the commands were executed."""
)
EDITOR_SYSTEM_PROMPT = os.environ.get(
    "EDITOR_SYSTEM_PROMPT",
    "You are a helpful assistant that helps users edit text files.",
)

class SessionLogger:
    def __init__(self, session_id: str, sessions_dir: str):
        self.session_id = session_id
        self.sessions_dir = sessions_dir
        self.logger = self._setup_logging()

        # Initialize token counters
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def _setup_logging(self) -> logging.Logger:
        """Configure logging for the session"""
        log_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(prefix)s - %(message)s"
        )
        log_file = os.path.join(self.sessions_dir, f"{self.session_id}.log")

        file_handler = RotatingFileHandler(
            log_file, maxBytes=1024 * 1024, backupCount=5
        )
        file_handler.setFormatter(log_formatter)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(log_formatter)

        logger = logging.getLogger(self.session_id)
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        logger.setLevel(logging.DEBUG)

        return logger

    def update_token_usage(self, input_tokens: int, output_tokens: int):
        """Update the total token usage."""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

    def log_total_cost(self):
        """Calculate and log the total cost based on token usage."""
        cost_per_million_input_tokens = 3.0  # $3.00 per million input tokens
        cost_per_million_output_tokens = 15.0  # $15.00 per million output tokens

        total_input_cost = (
            self.total_input_tokens / 1_000_000
        ) * cost_per_million_input_tokens
        total_output_cost = (
            self.total_output_tokens / 1_000_000
        ) * cost_per_million_output_tokens
        total_cost = total_input_cost + total_output_cost

        prefix = "📊 session"
        self.logger.info(
            f"Total input tokens: {self.total_input_tokens}", extra={"prefix": prefix}
        )
        self.logger.info(
            f"Total output tokens: {self.total_output_tokens}", extra={"prefix": prefix}
        )
        self.logger.info(
            f"Total input cost: ${total_input_cost:.6f}", extra={"prefix": prefix}
        )
        self.logger.info(
            f"Total output cost: ${total_output_cost:.6f}", extra={"prefix": prefix}
        )
        self.logger.info(f"Total cost: ${total_cost:.6f}", extra={"prefix": prefix})

class BashSession:
    def __init__(self, session_id: Optional[str] = None, no_agi: bool = False):
        """Initialize Bash session with optional existing session ID"""
        self.session_id = session_id or self._create_session_id()
        self.sessions_dir = SESSIONS_DIR
        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        self.messages = []
        self.current_tool_calls = []

        # Initialize a persistent environment dictionary for subprocesses
        self.environment = os.environ.copy()

        # Initialize logger placeholder
        self.logger = None

        # Set log prefix
        self.log_prefix = "🐚 bash"

        # Store the no_agi flag
        self.no_agi = no_agi

    def set_logger(self, session_logger: SessionLogger):
        """Set the logger for the session and store the SessionLogger instance."""
        self.session_logger = session_logger
        self.logger = logging.LoggerAdapter(
            session_logger.logger, {"prefix": self.log_prefix}
        )

    def _create_session_id(self) -> str:
        """Create a new session ID"""
        timestamp = datetime.now().strftime("%Y%m%d-%H:%M:%S-%f")
        return f"{timestamp}"

    def _handle_bash_command(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """Handle bash command execution"""
        try:
            command = tool_call.get("command")
            restart = tool_call.get("restart", False)

            if restart:
                self.environment = os.environ.copy()  # Reset the environment
                self.logger.info("Bash session restarted.")
                return {"content": "Bash session restarted."}

            if not command:
                self.logger.error("No command provided to execute.")
                return {"error": "No command provided to execute."}

            # Check if no_agi is enabled
            if self.no_agi:
                self.logger.info(f"Mock executing bash command: {command}")
                return {"content": f"🔍 Dry Run: Would execute command: {command}"}

            # Log the command being executed
            self.logger.info(f"Executing bash command: {command}")

            # Execute the command in a subprocess
            result = subprocess.run(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self.environment,
                text=True,
                executable="/bin/bash",
            )

            output = result.stdout.strip()
            error_output = result.stderr.strip()

            # Log the outputs
            if output:
                self.logger.info(
                    f"Command output:\n\n```output for '{command[:20]}...'\n{output}\n```"
                )
            if error_output:
                self.logger.error(
                    f"Command error output:\n\n```error for '{command}'\n{error_output}\n```"
                )

            if result.returncode != 0:
                error_message = error_output or "Command execution failed."
                return {"error": error_message}

            return {"content": output}

        except Exception as e:
            self.logger.error(f"Error in _handle_bash_command: {str(e)}")
            self.logger.error(traceback.format_exc())
            return {"error": str(e)}

    def process_tool_calls(self, tool_calls: List[anthropic.types.ContentBlock]) -> List[Dict[str, Any]]:
        """Process tool calls and return results"""
        results = []
        self.current_tool_calls = []  # Reset tool calls for this interaction

        for tool_call in tool_calls:
            if tool_call.type == "tool_use" and tool_call.name == "bash":
                self.logger.info(f"Bash tool call input: {tool_call.input}")
                # Store the tool call for UI display
                self.current_tool_calls.append({
                    "command": tool_call.input.get("command", ""),
                    "id": tool_call.id
                })

                result = self._handle_bash_command(tool_call.input)

                # Convert result to match expected tool result format
                is_error = False

                if result.get("error"):
                    is_error = True
                    tool_result_content = [{"type": "text", "text": result["error"]}]
                else:
                    tool_result_content = [
                        {"type": "text", "text": result.get("content", "")}
                    ]

                results.append(
                    {
                        "tool_call_id": tool_call.id,
                        "output": {
                            "type": "tool_result",
                            "content": tool_result_content,
                            "tool_use_id": tool_call.id,
                            "is_error": is_error,
                        },
                    }
                )

        return results

    def process_bash_command(self, bash_prompt: str, conversation_history: List[Dict[str, str]] = None) -> None:
        """Main method to process bash commands via the assistant"""
        try:
            # Convert conversation history to API format
            api_messages = []
            if conversation_history:
                for msg in conversation_history:
                    if msg["role"] in ["user", "assistant"]:
                        api_messages.append({
                            "role": msg["role"],
                            "content": [{"type": "text", "text": msg["content"]}]
                        })

            # Add dry run mode context to the prompt if enabled
            if self.no_agi:
                bash_prompt = f"[DRY RUN MODE ENABLED] {bash_prompt}"

            # Add the current message
            api_messages.append({
                "role": "user",
                "content": [{"type": "text", "text": bash_prompt}]
            })

            self.messages = api_messages
            self.logger.info(f"User input: {api_messages[-1]}")

            while True:
                response = self.client.beta.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=4096,
                    messages=self.messages,
                    tools=[{"type": "bash_20241022", "name": "bash"}],
                    system=BASH_SYSTEM_PROMPT,
                    betas=["computer-use-2024-10-22"],
                )

                # Extract token usage from the response
                input_tokens = getattr(response.usage, "input_tokens", 0)
                output_tokens = getattr(response.usage, "output_tokens", 0)
                self.logger.info(
                    f"API usage: input_tokens={input_tokens}, output_tokens={output_tokens}"
                )

                # Update token counts in SessionLogger
                self.session_logger.update_token_usage(input_tokens, output_tokens)

                self.logger.info(f"API response: {response.model_dump()}")

                # Convert response content to message params
                response_content = []
                for block in response.content:
                    if block.type == "text":
                        response_content.append({"type": "text", "text": block.text})
                    else:
                        response_content.append(block.model_dump())

                # Add assistant response to messages
                self.messages.append({"role": "assistant", "content": response_content})

                if response.stop_reason != "tool_use":
                    # Print the assistant's final response
                    print(response.content[0].text)
                    break

                tool_results = self.process_tool_calls(response.content)

                # Add tool results as user message
                if tool_results:
                    self.messages.append(
                        {"role": "user", "content": [tool_results[0]["output"]]}
                    )

                    if tool_results[0]["output"]["is_error"]:
                        self.logger.error(
                            f"Error: {tool_results[0]['output']['content']}"
                        )
                        break

            # After the execution loop, log the total cost
            self.session_logger.log_total_cost()

        except Exception as e:
            self.logger.error(f"Error in process_bash_command: {str(e)}")
            self.logger.error(traceback.format_exc())
            raise
