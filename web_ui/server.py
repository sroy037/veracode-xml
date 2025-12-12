import html
import re
import json
import shlex 
import os
import sys
import base64 
import hashlib # NEW: For passphrase hashing
import secrets # NEW: For secure hash comparison
from typing import Optional, Any, Dict

from flask import Flask, render_template, request # pyright: ignore[reportMissingImports]
from flask_socketio import SocketIO, emit, join_room, leave_room # pyright: ignore[reportMissingModuleSource]
import requests
from pathlib import Path

# --- Configuration ---
app = Flask(__name__)
# Load secret key from env or generate a random one
app.config['SECRET_KEY'] = os.getenv("FLASK_SECRET_KEY", os.urandom(24)) 
# Allow all origins for development/embed purposes
socketio = SocketIO(app, cors_allowed_origins="*") 

AGENT_API_URL = os.getenv("AGENT_API_URL", "http://localhost:8000/run")
REGION_MAP = {
    "commercial": "us",
    "european": "eu",
    # Accept direct CLI-style region tokens from the UI as well
    "us": "us",
    "eu": "eu",
    "us_fed": "us_fed",
}
DEFAULT_REGION_CLI_ARG = "us"

# --- Global State Management for Multi-Match and File Download ---
# Stores interactive context per session ID (sid).
# Context can store:
# - "matches" for multi-selection
# - "action": "select", "download", or "review_mitigation"
# - "agent_path" for pending file download
# - "base_cmd" for pending mitigation review command
# - "optional_args" (Crucially added for multi-match execution)
multi_match_context: Dict[str, Dict[str, Any]] = {} 

# --- Regex for Command Parsing ---
# Matches: veracli (build_list|build_info|detailed_report|summary_report|review_mitigation) -n NAME ...
# NOTE: review_mitigation is now included here.
VERACLI_HELPER_REGEX = re.compile(r"^veracli\s+(app_info|app_findings|build_list|build_info|detailed_report|summary_report|review_mitigation)\s+-n\s+.*", re.IGNORECASE)
# Regex to find the file path created by the veracli agent 
FILE_PATH_REGEX = re.compile(r"Report downloaded successfully:\s+(.*)", re.IGNORECASE)
# NEW: Regex to find the file path when the UI Helper runs the command (it sees the pre-download prompt)
FILE_GENERATED_REGEX = re.compile(r"File generated:\s*(.+?)\. Download now\? \[Y/n\]")


# --- Helper Functions (Command Parsing) ---

def parse_optional_args(query: str) -> str:
    """
    Extracts optional arguments (like -s ds, -b 1234) that follow the -n NAME argument
    from the original user query, ensuring they are properly quoted using shlex.quote().
    """
    optional_args = [] 
    try:
        # Use shlex.split to correctly tokenize the user's input, preserving quoted values
        tokens = shlex.split(query)
        name_index = -1
        
        # Find the index of the application name flag
        if '-n' in tokens:
            name_index = tokens.index('-n')
        elif '--app_name' in tokens:
            name_index = tokens.index('--app_name')
        
        if name_index != -1 and name_index + 2 <= len(tokens):
            # Captures all tokens *after* the application name (tokens[name_index + 1])
            for token in tokens[name_index + 2:]:
                # Use shlex.quote to safely wrap arguments with spaces (like "High & Above")
                optional_args.append(shlex.quote(token))
                
        # Join the safely quoted tokens back into a single argument string
        return " ".join(optional_args).strip()
    except Exception as e:
        # If parsing fails (e.g., malformed shlex input), return empty string and log error
        print(f"Error parsing optional arguments: {e}", file=sys.stderr)
        return ""


# --- Environment credential helpers ---

# --- NEW: Passphrase Hashing Helpers ---
def _hash_passphrase(passphrase: str, salt: str = "fixed_veracli_salt") -> str:
    """Calculates a secure hash for the passphrase using a fixed salt for simplicity."""
    # NOTE: In a real-world app, use bcrypt or PBKDF2 with a per-user/per-env unique salt.
    salted_pass = (passphrase + salt).encode('utf-8')
    return hashlib.sha256(salted_pass).hexdigest()

def _load_passphrase_hash(env_name: str) -> Optional[str]:
    """Loads the stored hash for a given environment name from the companion .hash file."""
    try:
        if '/' in env_name or '..' in env_name:
            return None

        target_dir = Path(os.getcwd()) / '.veracode'
        target_file = target_dir / f"{env_name}.hash"

        if target_file.exists():
            with target_file.open('r', encoding='utf-8') as fh:
                return fh.read().strip()
    except Exception as e:
        print(f"Error loading hash for {env_name}: {e}", file=sys.stderr)
    return None
# ---------------------------------------


def find_environment_files():
    """Return a list of (name, path) for credential files found in project .veracode and user ~/.veracode."""
    envs = {}
    project_dir = os.getcwd()
    search_paths = [
        Path(project_dir) / ".veracode",
        Path.home() / ".veracode",
    ]

    for sp in search_paths:
        if sp.exists() and sp.is_dir():
            for f in sp.glob('*.credentials'):
                # Skip example files that ship with the repo
                if f.name.lower() == 'example.credentials':
                    continue
                envs[f.stem] = str(f)

    return envs


def load_env_credentials(env_name: Optional[str]):
    """
    Load dotenv-style credentials from .veracode files.
    If env_name is provided, look for `.veracode/{env_name}.credentials` or `~/.veracode/{env_name}.credentials`.
    If env_name is None, fallback to `.veracode/credentials` and `~/.veracode/credentials`.
    Returns a tuple (creds_dict, path) where path is the file used or None.
    """
    candidates = []
    project_dir = os.getcwd()
    if env_name:
        candidates = [
            Path(project_dir) / ".veracode" / f"{env_name}.credentials",
            Path.home() / ".veracode" / f"{env_name}.credentials",
        ]
    else:
        candidates = [
            Path(project_dir) / ".veracode" / "credentials",
            Path.home() / ".veracode" / "credentials",
        ]

    for c in candidates:
        if c.exists() and c.is_file():
            creds = {}
            try:
                with c.open('r', encoding='utf-8') as fh:
                    for raw in fh:
                        line = raw.strip()
                        if not line or line.startswith('#'):
                            continue
                        if '=' not in line:
                            continue
                        k, v = line.split('=', 1)
                        k = k.strip()
                        v = v.strip().strip('"')
                        creds[k] = v
                return creds, str(c)
            except Exception as e:
                print(f"Error reading credentials file {c}: {e}", file=sys.stderr)
                return {}, None

    return {}, None

# --- Helper Functions for File Download (UPDATED) ---

def extract_detailed_report_path(agent_output: str) -> Optional[str]:
    """
    Extracts the local server file path from the agent's output if the report download was successful.
    Checks for two possible output formats and ensures an absolute path is returned.
    """
    # 1. Check for the primary "Report downloaded successfully:" line
    path_match = FILE_PATH_REGEX.search(agent_output)
    if path_match:
        # This path should be absolute (e.g., /app/report.xml)
        return path_match.group(1).strip()
        
    # 2. Check for the "File generated: <filename>. Download now? [Y/n]" line
    file_gen_match = FILE_GENERATED_REGEX.search(agent_output)
    if file_gen_match:
        extracted_path = file_gen_match.group(1).strip()
        
        # CRITICAL FIX: If the path is just a filename (i.e., not absolute),
        # prepend /app/ as the agent runs in a container with CWD = /app/
        if extracted_path and not extracted_path.startswith('/'):
            return f"/app/{extracted_path}"
        
        return extracted_path
        
    return None

def _execute_agent_file_retrieval(agent_path: str, env_name: Optional[str] = None, use_default: bool = False):
    """
    Executes a command on the remote agent to retrieve the file's raw content.
    Returns the file content string (expected to be base64 if binary) or raises an exception.
    """
    # The agent is instructed to read the file and return its base64 content
    retrieval_cmd = f"retrieve_agent_file {agent_path}"
    # START NEW LOGGING
    print(f"SERVER LOG: Sending file retrieval command to agent: {retrieval_cmd}", file=sys.stderr)
    # END NEW LOGGING
    
    try:
        post_payload = {"query": retrieval_cmd}
        # Attach credentials if requested either by explicit env_name or by use_default flag
        if env_name:
            creds, _ = load_env_credentials(env_name)
            if creds:
                post_payload["credentials"] = creds
        elif use_default:
            creds, _ = load_env_credentials(None)
            if creds:
                post_payload["credentials"] = creds

        retrieval_response = requests.post(AGENT_API_URL, json=post_payload)
        retrieval_response.raise_for_status()
        retrieval_data = retrieval_response.json()
        
        # START NEW LOGGING
        print(f"SERVER LOG: Agent response (Exit Code: {retrieval_data.get('exit_code')}) - Stderr: {retrieval_data.get('stderr', '')[:50]}...", file=sys.stderr)
        # END NEW LOGGING

        file_content_from_agent = retrieval_data.get("output", "")
        
        if not file_content_from_agent:
            # CRITICAL: Capture the agent's exit code and stderr for better diagnostics
            agent_stderr = retrieval_data.get('stderr', 'N/A')
            agent_exit_code = retrieval_data.get('exit_code', 'N/A')
            
            error_details = f"Agent Exit Code: {agent_exit_code}. Agent Stderr: {agent_stderr}"
            # UPDATED ERROR MESSAGE
            raise ValueError(f"Agent returned no file content for: {agent_path}. ({error_details})")
        
        return file_content_from_agent
        
    except requests.exceptions.RequestException as e:
        raise Exception(f"Failed to execute file retrieval on agent (API Error): {e}")
    except ValueError as e:
        # Re-raise the more detailed error message
        raise Exception(f"File retrieval error: {e}")


def handle_detailed_report_transfer_from_agent(sid: str, agent_file_path: str, file_content: str) -> bool:
    """
    Sends the file content retrieved from the agent to the client for download.
    Ensures XML content is base64 encoded for consistent client handling.
    """
    file_name = os.path.basename(agent_file_path)
    
    # 1. Determine MIME type from file extension
    if file_name.lower().endswith(".pdf"):
        mime_type = "application/pdf"
    elif file_name.lower().endswith(".xml"):
        mime_type = "application/xml"
    else:
        mime_type = "application/octet-stream"

    try:
        # # FIX: Ensure content is base64 encoded. Agent usually handles binary (PDF),
        # # but text files (XML) need explicit encoding here if returned as raw strings.
        # if mime_type == "application/xml":
        #     # Convert raw XML string content to bytes and then base64 encode it.
        #     encoded_content = base64.b64encode(file_content.encode('utf-8')).decode('utf-8')
        # else:
        #     # Assume content is already correctly formatted (e.g., base64 for PDF)
        encoded_content = file_content

        # 2. Emit the content to the client 
        socketio.emit('file_download', {
            'content': encoded_content, 
            'filename': file_name,
            'mimeType': mime_type
        }, room=sid)

        # 3. Notify the user of successful transfer
        socketio.emit('cli_output', {'data': f"\n✨ Report successfully downloaded to client: {file_name}\n"}, room=sid)
        
        return True

    except Exception as e:
        socketio.emit('cli_output', {'data': f"\n❌ Failed to send file {file_name} to client: {str(e)}\n"}, room=sid)
        
    return False


# --- Helper Functions (execute_agent_command_stream) ---

def format_matches_for_display(matches):
    """Formats the list of matches (from helper's JSON output) into CLI-style output."""
    output = ["\n⚠️ Multiple matches found. Please select an option:"]
    
    for match in matches:
        # Ensure we display the REST ID (GUID) or XML ID based on match data
        identifier = f"GUID: {match['guid']}" if match['guid'] != '-' else f"ID: {match['id']}"
        output.append(f"  [{match['index']}] {match['name']:<50} ({identifier}) Last Scan: {match.get('last_scan', '-')}")
        
    return "\n".join(output)

# CRITICAL FIX: Added optional_args parameter to pass arguments reliably
def execute_agent_command_stream(command_str: str, sid: str, is_helper_call: bool = False, optional_args: str = "", current_region_cli_arg: str = "us", env_name: Optional[str] = None, use_default: bool = False):
    """
    Executes the command against the agent API and streams the output 
    back to the client via SocketIO events.
    """
    
    # If an environment name was provided by the UI, load its credentials and attach
    creds_payload = {}
    # Load credentials only if env_name provided or the user explicitly requested the default
    if env_name:
        creds, _ = load_env_credentials(env_name)
        if creds:
            creds_payload = creds
    elif use_default:
        # User explicitly requested the default credentials (./.veracode/credentials or ~/.veracode/credentials)
        creds, path = load_env_credentials(None)
        if creds:
            creds_payload = creds

    # Determine effective region: prefer explicit region from credentials file, else infer from env_name, else keep UI region
    effective_region_cli_arg = current_region_cli_arg
    # 1) check credentials for a REGION key (case-insensitive)
    creds_region = None
    for k, v in creds_payload.items():
        if k.lower() == 'region':
            creds_region = v
            break

    if creds_region:
        mapped = REGION_MAP.get(creds_region.strip().lower())
        if mapped:
            effective_region_cli_arg = mapped
        else:
            # fallback: accept short values like 'us'/'eu' if present
            if creds_region.strip().lower() in REGION_MAP:
                effective_region_cli_arg = REGION_MAP[creds_region.strip().lower()]
    else:
        # 2) infer from env_name convention (e.g., 'eu-default' -> eu)
        if env_name:
            name_l = env_name.lower()
            if name_l.startswith('eu') or name_l.startswith('europe') or '-eu' in name_l:
                effective_region_cli_arg = 'eu'
            elif name_l.startswith('us') or name_l.startswith('com') or 'commercial' in name_l:
                effective_region_cli_arg = 'us'

    # Ensure the region CLI arg is included so the agent and helper honor the selected region.
    lower_cmd = command_str.lower()
    if "--region" not in lower_cmd and " -r " not in lower_cmd:
        command_str = f"{command_str} --region {effective_region_cli_arg}"

    payload = {"query": command_str}
    if creds_payload:
        payload["credentials"] = creds_payload
    
    # 1. Pre-extract command type from the original input string (if it's a helper call)
    original_command_type = None
    if is_helper_call:
        cleaned_command_str = command_str.strip() 
        match_inferred = VERACLI_HELPER_REGEX.match(cleaned_command_str)
        if match_inferred:
            original_command_type = match_inferred.group(1)
            
    try:
        # Emit a small non-sensitive debug line to the client so the UI shows which env (if any) and region are used
        # Emit whether credentials are being forwarded. Don't include secret values.
        if creds_payload:
            socketio.emit('cli_output', {'data': f"\n🔐 Forwarding credentials from environment: {env_name if env_name else 'default'} (region: {effective_region_cli_arg})\n"}, room=sid)
        else:
            if use_default:
                socketio.emit('cli_output', {'data': f"\n⚠️ Requested default credentials but none found (searched ./.veracode/credentials and ~/.veracode/credentials). Using region: {effective_region_cli_arg}\n"}, room=sid)
            else:
                socketio.emit('cli_output', {'data': f"\n🔐 No environment credentials forwarded (using region: {effective_region_cli_arg})\n"}, room=sid)

        response = requests.post(AGENT_API_URL, json=payload)
        response.raise_for_status() 
        data = response.json() 

        output = data.get("output", "")
        stderr = data.get("stderr", "")
        exit_code = data.get("exit_code", 0)

        if isinstance(output, list):
            output = "\n".join(output)
        if isinstance(stderr, list):
            stderr = "\n".join(stderr)

        # Use final_output and final_cmd variables for both helper and direct execution
        final_output = output
        final_stderr = stderr
        final_exit_code = exit_code
        final_cmd = command_str
        
        # Initialize command_type for scope
        command_type = None

        # --- Intercept Helper Task Output (JSON/Error) ---
        if is_helper_call:
            
            try:
                helper_result = json.loads(output.strip())
                status = helper_result.get("status")
                
                api_type = helper_result.get("api_type", "rest") 
                # Use original_command_type as a reliable fallback
                command_type = helper_result.get("command", original_command_type)
                
                # FIX: Explicitly use original command type for XML/Unique match 
                if api_type == "xml" and original_command_type:
                    command_type = original_command_type
                
                if status == "unique":
                    app_name = helper_result.get("app_name") 
                    app_guid = helper_result.get("guid") 
                    # CRITICAL FIX: The helper outputs 'app_id', not 'id'.
                    app_id = helper_result.get("app_id")

                    final_cmd_build = ""
                    match_id = ""
                    
                    # NOTE: optional_args were passed to this function via handle_command

                    # REST Final Execution for Unique Match
                    if api_type == "rest" and app_guid:
                        match_id = f"GUID: {app_guid}"

                        if command_type in ["summary_report", "app_findings"]:
                            # Use optional_args from the function call
                            final_cmd_build = f"veracli {command_type} -g {app_guid} -t REST {optional_args} --region {effective_region_cli_arg}"
                        else:
                            final_cmd_build = f"veracli app_info_ui_helper --guid {app_guid} --region {effective_region_cli_arg}"

                    # CRITICAL FIX: Changed -a to -i based on user's successful execution log
                    elif api_type == "xml" and app_id and command_type:
                        # XML/App ID execution
                        # Use optional_args from the function call
                        # NOTE: Using -i is correct for XML app info/report commands
                        final_cmd_build = f"veracli {command_type} -i {app_id} {optional_args} --region {effective_region_cli_arg}"
                        match_id = f"ID: {app_id}"
                    
                    if final_cmd_build:
                        final_cmd = final_cmd_build # Set final_cmd for use outside this block
                        socketio.emit('cli_output', {'data': f"\n✅ Unique match found (Name: {app_name}, {match_id}). Executing: {final_cmd}\n"}, room=sid)
                        
                        # Execute the final lookup command 
                        payload_final = {"query": final_cmd}
                        if creds_payload:
                            payload_final["credentials"] = creds_payload
                        response_final = requests.post(AGENT_API_URL, json=payload_final)
                        response_final.raise_for_status()
                        data_final = response_final.json()
                        
                        final_output = data_final.get("output", "")
                        final_stderr = data_final.get("stderr", "")
                        final_exit_code = data_final.get("exit_code", 0)
                        
                        if isinstance(final_output, list): final_output = "\n".join(final_output)
                        if isinstance(final_stderr, list): final_stderr = "\n".join(final_stderr)
                        
                        
                        # --- Handle Review Mitigation Interactive Prompt ---
                        mitigation_prompt_text = "Enter numbers of issues to fetch mitigation info (comma-separated):"
                        
                        if command_type == "review_mitigation" and final_exit_code != 0 and mitigation_prompt_text in final_output:
                            
                            # Store context and prompt user 
                            multi_match_context[sid] = {
                                "action": "review_mitigation",
                                "base_cmd": final_cmd, # The command that generated the list and crashed
                                "region": effective_region_cli_arg,
                                "env_name": env_name,
                                "use_default": use_default
                            }
                            
                            # Extract and stream output *up to* the interactive prompt
                            prompt_index = final_output.find(mitigation_prompt_text)
                            output_to_stream = final_output[:prompt_index]

                            # Stream the output *up to* the interactive prompt
                            for chunk in output_to_stream.splitlines(keepends=True):
                                socketio.emit('cli_output', {'data': html.escape(chunk)}, room=sid)

                            socketio.emit('cli_output', {'data': f"\n➡️ Enter issue numbers (e.g., 1, 3, 5) to review mitigation details:\n"}, room=sid)
                            socketio.emit('cli_output', {'data': f"\n(Exit Code: {final_exit_code})\n"}, room=sid)
                            socketio.emit('cli_prompt', {'data': 'ISSUE IDS: '}, room=sid)
                            return # EXIT: Wait for user input
                        
                        # --- Handle Detailed Report Download Prompt ---
                        is_detailed_report = re.match(r"^veracli detailed_report\s+.*", final_cmd, re.IGNORECASE)
                        agent_path = extract_detailed_report_path(final_output)

                        if is_detailed_report and final_exit_code == 0 and agent_path:
                            # Store context and prompt user instead of immediate download
                            multi_match_context[sid] = {
                                "action": "download",
                                "agent_path": agent_path,
                                "env_name": env_name,
                                "region": effective_region_cli_arg,
                                "use_default": use_default
                            }
                            file_name = os.path.basename(agent_path)
                            
                            # Stream the output *up to* the download success/prompt message
                            for chunk in final_output.splitlines(keepends=True):
                                if "Report downloaded successfully:" in chunk or "File generated:" in chunk:
                                    break # Stop streaming here
                                socketio.emit('cli_output', {'data': html.escape(chunk)}, room=sid)

                            socketio.emit('cli_output', {'data': f"\n📄 File generated: {file_name}. Download now? [Y/n]:\n"}, room=sid)
                            socketio.emit('cli_output', {'data': f"\n(Exit Code: {final_exit_code})\n"}, room=sid)
                            socketio.emit('cli_prompt', {'data': 'DOWNLOAD [Y/n]: '}, room=sid)
                            return # EXIT: Wait for user input
                        
                        # Stream the standard output if not a successful download OR mitigation prompt
                        for chunk in final_output.splitlines(keepends=True):
                            socketio.emit('cli_output', {'data': html.escape(chunk)}, room=sid)

                        if final_stderr and final_stderr.strip().lower() not in ('none', ''):
                            socketio.emit('cli_output', {'data': f"\n--- ERROR/STDERR ---\n{html.escape(final_stderr)}\n"}, room=sid)
                        
                        socketio.emit('cli_output', {'data': f"\n(Exit Code: {final_exit_code})\n"}, room=sid)
                        
                        # Signal the prompt and RETURN
                        socketio.emit('cli_prompt', {'data': '> '}, room=sid)
                        return 
                    else:
                        # *** IMPROVED DIAGNOSTIC ERROR MESSAGE HERE ***
                        missing_data = []
                        if api_type == "xml" and not app_id:
                            # This should now be correctly caught due to the fix above
                            missing_data.append("App ID (expected for XML command)")
                        if api_type == "rest" and not app_guid:
                            missing_data.append("App GUID (expected for REST command)")
                        if not command_type:
                            missing_data.append("Command Type")
                            
                        error_detail = ""
                        if missing_data:
                            error_detail = f"Details: The helper returned 'unique' status but is missing the following required keys: {', '.join(missing_data)}."
                        else:
                             error_detail = "Details: The unique match data failed to construct a valid final command."
                             
                        # Emit a more detailed error message to help diagnose the flutter issue
                        socketio.emit('cli_output', {'data': f"\n⚠️ Missing required data for final lookup (Type: {api_type}). {error_detail}\n"}, room=sid)
                        socketio.emit('cli_prompt', {'data': '> '}, room=sid)
                        return
                    
                elif status == "multiple":
                    matches = helper_result.get("matches")
                    
                    # CRITICAL FIX: Store optional_args here so they can be used after selection
                    multi_match_context[sid] = {
                        "action": "select", # Explicitly set action to select
                        "matches": matches,
                        "api_type": api_type,
                        "command": command_type, 
                        "optional_args": optional_args, # <<< Storing optional args reliably
                        "env_name": env_name,
                        "region": effective_region_cli_arg,
                        "use_default": use_default
                    } 
                    
                    display_output = format_matches_for_display(matches)
                    socketio.emit('cli_output', {'data': html.escape(display_output)}, room=sid)
                    socketio.emit('cli_output', {'data': "\n\n➡️ Enter the selection number below:\n"}, room=sid)
                    socketio.emit('cli_prompt', {'data': 'SELECT: '}, room=sid) 
                    return 

                elif status == "no_match":
                    socketio.emit('cli_output', {'data': f"\n❌ No applications found matching '{helper_result.get('app_name')}'.\n"}, room=sid)
                    output = ""
                
                elif status == "error":
                    socketio.emit('cli_output', {'data': f"\n❌ UI Helper Error: {helper_result.get('message', 'Unknown error')}\n"}, room=sid)
                    output = ""
                
            except json.JSONDecodeError as e:
                socketio.emit('cli_output', {'data': f"\n⚠️ Helper output was not valid JSON (Error: {e}).\nRaw output below:\n"}, room=sid)
                
                if stderr:
                     socketio.emit('cli_output', {'data': f"\n--- STDERR (Agent Execution Error) ---\n{html.escape(stderr)}\n"}, room=sid)

                socketio.emit('cli_prompt', {'data': '> '}, room=sid)
                return 
        
        # --- Handle Review Mitigation Interactive Prompt (Direct Execution) ---
        is_review_mitigation = re.match(r"^veracli review_mitigation\s+.*", final_cmd, re.IGNORECASE)
        mitigation_prompt_text = "Enter numbers of issues to fetch mitigation info (comma-separated):"
        
        if is_review_mitigation and final_exit_code != 0 and mitigation_prompt_text in final_output:
            
            # Store context and prompt user 
            multi_match_context[sid] = {
                "action": "review_mitigation",
                "base_cmd": final_cmd, # The command that generated the list and crashed
                "region": effective_region_cli_arg,
                "env_name": env_name,
                "use_default": use_default
            }
            
            # Extract and stream output *up to* the interactive prompt
            prompt_index = final_output.find(mitigation_prompt_text)
            output_to_stream = final_output[:prompt_index]

            # Stream the output *up to* the interactive prompt
            for chunk in output_to_stream.splitlines(keepends=True):
                socketio.emit('cli_output', {'data': html.escape(chunk)}, room=sid)

            socketio.emit('cli_output', {'data': f"\n➡️ Enter issue numbers (e.g., 1, 3, 5) to review mitigation details:\n"}, room=sid)
            socketio.emit('cli_output', {'data': f"\n(Exit Code: {final_exit_code})\n"}, room=sid)
            socketio.emit('cli_prompt', {'data': 'ISSUE IDS: '}, room=sid)
            return # EXIT: Wait for user input
        
        # --- Handle Detailed Report Download Prompt (Direct Execution) ---
        is_detailed_report = re.match(r"^veracli detailed_report\s+.*", command_str, re.IGNORECASE)
        agent_path = extract_detailed_report_path(output)

        if is_detailed_report and exit_code == 0 and agent_path:
            # Store context and prompt user instead of immediate download
            multi_match_context[sid] = {
                "action": "download",
                "agent_path": agent_path,
                "env_name": env_name,
                "region": effective_region_cli_arg,
                "use_default": use_default
            }
            file_name = os.path.basename(agent_path)
            
            # Stream output up to the success message
            for chunk in output.splitlines(keepends=True):
                if "Report downloaded successfully:" in chunk or "File generated:" in chunk:
                    break # Stop streaming here
                socketio.emit('cli_output', {'data': html.escape(chunk)}, room=sid)

            socketio.emit('cli_output', {'data': f"\n📄 File generated: {file_name}. Download now? [Y/n]:\n"}, room=sid)
            socketio.emit('cli_output', {'data': f"\n(Exit Code: {exit_code})\n"}, room=sid)
            socketio.emit('cli_prompt', {'data': 'DOWNLOAD [Y/n]: '}, room=sid)
            return # EXIT: Wait for user input

        # --- Standard Output Stream (for non-download or failed commands) ---
        for chunk in final_output.splitlines(keepends=True):
            socketio.emit('cli_output', {'data': html.escape(chunk)}, room=sid)

        # --- Final Prompts ---
        if final_stderr and final_stderr.strip().lower() not in ('none', ''):
            socketio.emit('cli_output', {'data': f"\n--- ERROR/STDERR ---\n{html.escape(final_stderr)}\n"}, room=sid)
        
        socketio.emit('cli_output', {'data': f"\n(Exit Code: {final_exit_code})\n"}, room=sid)
        # Signal the end of the command execution and return to avoid duplicate streaming below
        socketio.emit('cli_prompt', {'data': '> '}, room=sid)
        return
        
    except requests.exceptions.HTTPError as e:
        error_msg = f"\n❌ HTTP Error {response.status_code}: {str(e)}\n"
        socketio.emit('cli_output', {'data': error_msg}, room=sid)
        socketio.emit('cli_prompt', {'data': '> '}, room=sid)
        return
    except Exception as e:
        error_msg = f"\n❌ General Error: {str(e)}\n"
        socketio.emit('cli_output', {'data': error_msg}, room=sid)
        socketio.emit('cli_prompt', {'data': '> '}, room=sid)
        return
        
    # Check if the output is the special JSON payload for credential rotation
    try:
        data = json.loads(final_output)
        if data.get("success") and "VERACODE_API_KEY_ID" in data:
            
            # 1. CRITICAL: Set the environment variables in the server process
            os.environ["VERACODE_API_KEY_ID"] = data["VERACODE_API_KEY_ID"]
            os.environ["VERACODE_API_KEY_SECRET"] = data["VERACODE_API_KEY_SECRET"]
            
            # 2. Stream the simple success message back to the client
            socketio.emit('cli_output', {'data': "\n✅ Credentials successfully rotated and set on the server."}, room=sid)
            
            # 3. CRITICAL: Signal to the client to unlock the UI
            socketio.emit('cli_output', {'data': "Credentials successfully rotated."}, room=sid)

            # NOTE: We return here, skipping the general streaming loop
            return
            
    except json.JSONDecodeError:
        # Not a JSON payload, proceed to stream as regular output
        pass

    # Stream the standard output (if not intercepted as rotation JSON)
    for chunk in final_output.splitlines(keepends=True):
        socketio.emit('cli_output', {'data': html.escape(chunk)}, room=sid)

    # Signal the end of the command execution and return to avoid duplicate streaming below
    socketio.emit('cli_prompt', {'data': '> '}, room=sid)
    return

# --- WebSocket Event Handlers ---

@socketio.on('connect')
def handle_connect():
    join_room(request.sid)
    emit('cli_output', {'data': 'Veracli Shell Connected. Type a command or click a button to begin.\n'})
    emit('cli_prompt', {'data': '> '})

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in multi_match_context:
        del multi_match_context[request.sid]
    leave_room(request.sid)

@socketio.on('command')
def handle_command(data):
    """Receives command from the client and executes it."""
    # Debug: emit received payload overview (non-sensitive)
    # try:
    #     recv_env = data.get('env_name') if isinstance(data, dict) else None
    #     recv_region = data.get('region_select') if isinstance(data, dict) else None
    #     recv_use_default = None
    #     socketio.emit('cli_output', {'data': f"\n[DEBUG] Received command payload - env_name: '{recv_env}', region_select: '{recv_region}', use_default: '{recv_use_default}'\n"}, room=request.sid)
    # except Exception:
    #     pass
    user_cmd = data.get('cmd', '').strip()
    sid = request.sid
    region_ui = data.get('region_select', 'Commercial').strip().lower() # Default to 'Commercial'
    current_region_cli_arg = REGION_MAP.get(region_ui, DEFAULT_REGION_CLI_ARG)
    use_default = False
    env_name = None if use_default else (data.get('env_name', '') or None)

    if not user_cmd:
        emit('cli_prompt', {'data': '> '}, room=sid)
        return

    emit('cli_clear_prompt', {}, room=sid)
    
    # --- 1. Check for Pending Download Action ---
    if sid in multi_match_context and multi_match_context[sid].get("action") == "download":
        
        context = multi_match_context.pop(sid) # Remove context immediately to prevent re-trigger
        agent_path = context["agent_path"]
        
        if user_cmd.lower() in ('y', 'yes', ''): # Accept 'Y' or empty input as confirmation
            socketio.emit('cli_output', {'data': f"User selected Y. Retrieving file from agent...\n"}, room=sid)
            try:
                # STEP 2: RETRIEVE CONTENT from the remote agent (preserve selected env/use_default)
                file_content = _execute_agent_file_retrieval(agent_path, context.get('env_name'), False)
                
                # STEP 3: TRANSFER to client
                handle_detailed_report_transfer_from_agent(sid, agent_path, file_content)
                
            except Exception as e:
                socketio.emit('cli_output', {'data': f"\n❌ Download failed: {str(e)}\n"}, room=sid)

        elif user_cmd.lower() in ('n', 'no'):
            file_name = os.path.basename(agent_path)
            socketio.emit('cli_output', {'data': f"Download of {file_name} skipped.\n"}, room=sid)
        else:
            # Invalid input: Restore context and re-prompt
            multi_match_context[sid] = context
            file_name = os.path.basename(agent_path)
            socketio.emit('cli_output', {'data': f"\nInvalid input. File generated: {file_name}. Download now? [Y/n]:\n"}, room=sid)
            socketio.emit('cli_prompt', {'data': 'DOWNLOAD [Y/n]: '}, room=sid)
            return

        # Always return to standard prompt after handling download choice
        socketio.emit('cli_prompt', {'data': '> '}, room=sid)
        return
    
    # --- 1a. Check for Pending Review Mitigation Action ---
    if sid in multi_match_context and multi_match_context[sid].get("action") == "review_mitigation":
        
        context = multi_match_context.pop(sid) # Remove context immediately 
        issue_ids = user_cmd.strip()
        base_cmd = context["base_cmd"]
        
        if not issue_ids:
            socketio.emit('cli_output', {'data': "No issue IDs provided. Returning to main prompt.\n"}, room=sid)
        else:
            # Build the new command by appending --issue_ids 
            final_mitigation_cmd = f"{base_cmd} --issue_ids {issue_ids}"
            
            socketio.emit('cli_output', {'data': f"\nExecuting mitigation review for IDs: {issue_ids}\nCommand: {final_mitigation_cmd}\n"}, room=sid)
            
            # Execute the final, non-interactive command using stored context env_name and stored region
            mitigation_region = context.get('region', current_region_cli_arg)
            execute_agent_command_stream(final_mitigation_cmd, sid, is_helper_call=False, current_region_cli_arg=mitigation_region, env_name=context.get('env_name'), use_default=False)
            return # EXIT: execute_agent_command_stream will handle the prompt at the end
            
        # If execution skipped (no issue IDs) or successful execution finished, return to main prompt
        socketio.emit('cli_prompt', {'data': '> '}, room=sid)
        return
    
    # --- 2. Check for Selection Input (Action: 'select') ---
    if sid in multi_match_context and multi_match_context[sid].get("action") == "select" and user_cmd.isdigit():
        selection_num = int(user_cmd)
        context = multi_match_context.pop(sid)
        
        matches = context["matches"]
        api_type = context["api_type"]
        command_type = context["command"]
        
        # Retrieve optional arguments from context (CRITICAL: now reliably stored)
        optional_args = context.get("optional_args", "") 

        selected_match = next((m for m in matches if m['index'] == selection_num), None)

        if selected_match:
            app_name = selected_match['name']
            app_guid = selected_match.get('guid') 
            app_id = selected_match.get('id')     
            
            final_cmd = ""
            
            if api_type == "rest" and app_guid:
                region_to_use = context.get('region', current_region_cli_arg)
                if command_type in ["summary_report", "detailed_report", "review_mitigation", "app_findings"]:
                    final_cmd = f"veracli {command_type} -g {app_guid} -t REST {optional_args} --region {region_to_use}" 
                else:
                    final_cmd = f"app_info_ui_helper --guid {app_guid} --region {region_to_use}" 

            # CRITICAL FIX: Changed -a to -i
            elif api_type == "xml" and app_id and command_type:
                region_to_use = context.get('region', current_region_cli_arg)
                final_cmd = f"veracli {command_type} -i {app_id} {optional_args} --region {region_to_use}" 
            else:
                 # Re-using the diagnostic improvement for selection failure
                 missing_data = []
                 if api_type == "xml" and not app_id:
                     missing_data.append("App ID (expected for XML command)")
                 if api_type == "rest" and not app_guid:
                     missing_data.append("App GUID (expected for REST command)")
                 
                 error_detail = f"Details: Selection succeeded but the match data is missing: {', '.join(missing_data)}."
                 
                 socketio.emit('cli_output', {'data': f"\n⚠️ Missing required data for final lookup (Type: {api_type}). {error_detail}\n"}, room=sid)
                 socketio.emit('cli_prompt', {'data': '> '}, room=sid)
                 return
            
            socketio.emit('cli_output', {'data': f"\n✅ Selection '{selection_num}' ({app_name}) made. Executing: {final_cmd}\n"}, room=sid)
            
            # Use env_name and stored region from selection context to ensure the same credentials/region are used
            selection_region = context.get('region', current_region_cli_arg)
            execute_agent_command_stream(final_cmd, sid, is_helper_call=False, current_region_cli_arg=selection_region, env_name=context.get('env_name'), use_default=False)
        else:
            socketio.emit('cli_output', {'data': "\n❌ Invalid selection number. Please try the command again.\n"}, room=sid)
            socketio.emit('cli_prompt', {'data': '> '}, room=sid)
        return

    # 3. Check for Helper Commands (REST and XML)
    #match_name_rest = APP_INFO_REST_NAME_REGEX.match(user_cmd)
    match_name_xml = VERACLI_HELPER_REGEX.match(user_cmd)

    if match_name_xml: 
        helper_cmd = user_cmd 
        
        # Extract optional arguments from the original command
        optional_args = parse_optional_args(user_cmd)
        
        socketio.emit('cli_output', {'data': f"\n🔎 Checking for matches via UI Helper (Cmd: {helper_cmd})....\n"}, room=sid)
        
        # Pass optional_args and the current region to the stream function
        execute_agent_command_stream(helper_cmd, sid, is_helper_call=True, optional_args=optional_args, current_region_cli_arg=current_region_cli_arg, env_name=env_name, use_default=False)
        
        return

    # 4. Standard Command Execution (Fallthrough for other commands)
    if sid in multi_match_context:
        del multi_match_context[sid] 
        
    execute_agent_command_stream(user_cmd, sid, is_helper_call=False, current_region_cli_arg=current_region_cli_arg, env_name=env_name, use_default=False)
    return

# --- Flask Routes (Only for initial page load) ---
@app.route("/", methods=["GET"])
def index():
    # Assuming the HTML content is served via a template named 'chat.html'
    return render_template("chat.html")


@app.route('/environments', methods=['GET'])
def list_environments():
    """Return a JSON list of available environment names discovered under .veracode/ and ~/.veracode/."""
    envs = find_environment_files()
    names = sorted(envs.keys())
    return json.dumps(names), 200, {'Content-Type': 'application/json'}


@app.route('/environments', methods=['POST'])
def create_environment():
    """Create a new environment credentials file AND a companion hash file.

    Expects JSON: { "name": "dev", "content": "KEY=VALUE...", "passphrase": "secret" }
    """
    try:
        data = request.get_json(force=True)
        name = data.get('name')
        content = data.get('content', '')
        # --- NEW: Get passphrase ---
        passphrase = data.get('passphrase')

        if not name or '/' in name or '..' in name:
            return json.dumps({'error': 'Invalid environment name'}), 400, {'Content-Type': 'application/json'}
        
        # --- NEW: Check for passphrase ---
        if not passphrase:
            return json.dumps({'error': 'Passphrase is required for environment security.'}), 400, {'Content-Type': 'application/json'}

        target_dir = Path(os.getcwd()) / '.veracode'
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Save Credentials
        target_cred_file = target_dir / f"{name}.credentials"
        with target_cred_file.open('w', encoding='utf-8') as fh:
            fh.write(content)

        # 2. Save Passphrase Hash
        target_hash_file = target_dir / f"{name}.hash"
        passphrase_hash = _hash_passphrase(passphrase)
        with target_hash_file.open('w', encoding='utf-8') as fh:
            fh.write(passphrase_hash)

        return json.dumps({'ok': True, 'path': str(target_cred_file)}), 201, {'Content-Type': 'application/json'}
    except Exception as e:
        return json.dumps({'error': str(e)}), 500, {'Content-Type': 'application/json'}

# --- NEW: Authorization Endpoint ---
@app.route('/authorize_environment', methods=['POST'])
def authorize_environment():
    """Checks the provided passphrase against the stored hash for an environment."""
    try:
        data = request.get_json(force=True)
        name = data.get('name')
        passphrase = data.get('passphrase')
        
        if not name or '/' in name or '..' in name:
            return json.dumps({'error': 'Invalid environment name'}), 400, {'Content-Type': 'application/json'}
        
        if not passphrase:
            return json.dumps({'error': 'Passphrase is required for authorization.'}), 400, {'Content-Type': 'application/json'}

        # 1. Load the stored hash
        stored_hash = _load_passphrase_hash(name)
        if not stored_hash:
            return json.dumps({'error': f"Environment '{name}' not found or no security hash available. Please re-create it."}), 404, {'Content-Type': 'application/json'}
        
        # 2. Compute the hash of the provided passphrase
        input_hash = _hash_passphrase(passphrase)
        
        # 3. Compare hashes securely
        if secrets.compare_digest(stored_hash, input_hash):
            return json.dumps({'ok': True}), 200, {'Content-Type': 'application/json'}
        else:
            return json.dumps({'error': 'Invalid passphrase.'}), 401, {'Content-Type': 'application/json'}

    except Exception as e:
        return json.dumps({'error': str(e)}), 500, {'Content-Type': 'application/json'}
# -----------------------------------


@app.route('/environments/<env_name>', methods=['GET'])
def get_environment(env_name):
    """Return the raw credential file content for a single environment name, if present."""
    try:
        if '/' in env_name or '..' in env_name:
            return json.dumps({'error': 'Invalid environment name'}), 400, {'Content-Type': 'application/json'}

        creds, path = load_env_credentials(env_name)
        if path is None:
            return json.dumps({'error': 'Not found'}), 404, {'Content-Type': 'application/json'}

        # Rebuild the original file content (KEY=VALUE lines). Preserve ordering as best-effort.
        lines = [f"{k}={v}" for k, v in creds.items()]
        content = "\n".join(lines)
        return json.dumps({'ok': True, 'content': content}), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        return json.dumps({'error': str(e)}), 500, {'Content-Type': 'application/json'}


@app.route('/environments/<env_name>', methods=['DELETE'])
def delete_environment(env_name):
    """Delete environment file and its companion hash file from project .veracode/ if they exist."""
    try:
        if '/' in env_name or '..' in env_name:
            return json.dumps({'error': 'Invalid environment name'}), 400, {'Content-Type': 'application/json'}

        target_cred_file = Path(os.getcwd()) / '.veracode' / f"{env_name}.credentials"
        # --- NEW: Target hash file ---
        target_hash_file = Path(os.getcwd()) / '.veracode' / f"{env_name}.hash"
        
        deleted_count = 0
        if target_cred_file.exists():
            target_cred_file.unlink()
            deleted_count += 1
            
        # --- NEW: Delete hash file ---
        if target_hash_file.exists():
            target_hash_file.unlink()
            deleted_count += 1

        if deleted_count > 0:
            return json.dumps({'ok': True}), 200, {'Content-Type': 'application/json'}
        else:
            return json.dumps({'error': 'Not found'}), 404, {'Content-Type': 'application/json'}
    except Exception as e:
        return json.dumps({'error': str(e)}), 500, {'Content-Type': 'application/json'}

if __name__ == "__main__":
    socketio.run(
        app, 
        host="0.0.0.0", 
        port=3000, 
        debug=False, 
        allow_unsafe_werkzeug=True
    )