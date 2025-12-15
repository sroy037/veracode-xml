from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import Any, Tuple, List, Dict, Optional
import subprocess
import re
import os
import shlex 
import sys
import json
import base64 # ADDED: Required for file encoding

app = FastAPI(title="Veracli Agent API")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/version")
def version():
    return {"veracli_agent_version": "1.0.0"}

class Query(BaseModel):
    query: str
    # Optional per-request credentials forwarded from the web UI server
    credentials: Optional[Dict[str, str]] = None

# --- Helper Functions (Command Building) ---

def get_target_guid(q: str) -> str | None:
    """Extracts a GUID from the query string."""
    match = re.search(r"guid\s+([0-9a-fA-F\-]+)", q, re.IGNORECASE)
    return match.group(1).strip() if match else None

def get_target_name(q: str, app_name_arg: str = None) -> str | None:
    """
    Extracts the application name from the query.
    Looks for the name following specific command contexts.
    """
    if app_name_arg:
        return app_name_arg

    # Regex to capture app name after command context
    match_context = re.search(r"(app_info|build_list|build_info|detailed_report|summary_report|review_mitigation)\s+([\w\s/-]+)", q, re.IGNORECASE)
    if match_context:
        name = match_context.group(2).strip()
        # Clean up any trailing API type indicators or format flags (like -f XML)
        name = re.sub(r'\s+(rest|xml|guid|\-f\s+(xml|pdf))', '', name, flags=re.IGNORECASE).strip()
        return name if name else None

    return None

def get_api_type_and_clean_query(q: str) -> Tuple[str, str]:
    """Identifies the API type (REST/XML) and removes the indicator from the query."""
    q_lower = q.lower()
    patterns = {"rest api": "REST", "rest": "REST"}
    
    api_type = ""
    cleaned_q = q
    
    for pattern, type_name in patterns.items():
        if pattern in q_lower:
            api_type = type_name
            cleaned_q = q.replace(pattern, "", 1).strip()
            break

    return api_type, cleaned_q

def build_command(query: str, app_id: str = None, app_name: str = None, region: str = "us") -> list[str]:
    """
    Translates a natural language query into a list of shell arguments, 
    either for the 'veracli' tool or for the internal helper script.
    """
    
    # 1. Handle explicit 'veracli' prefix commands
    if query.strip().lower().startswith("veracli"):
        command_tokens = shlex.split(query.strip())
        
        # 🔑 Critical: Intercept ALL Name-based lookups that need helper support
        if len(command_tokens) >= 4 and command_tokens[0].lower() == "veracli":
            command_type = command_tokens[1].lower()
            
            is_name_lookup = command_tokens[2] in ("-n", "--app_name")
            
            if is_name_lookup:
                target_name_raw = command_tokens[3]
                
                # Check for XML/REST API type to decide the helper parameters
                api_mode = "xml"
                
                # Check if this is a REST command
                if "-t" in command_tokens:
                    try:
                        t_index = command_tokens.index("-t")
                        if command_tokens[t_index + 1].lower() == "rest":
                            api_mode = "rest"
                    except IndexError:
                        pass
                
                # List of XML commands that must resolve -n to an App ID (-a) non-interactively
                XML_NAME_LOOKUP_REQUIRED = (
                    "build_list", "build_info", 
                    "detailed_report", "summary_report", 
                    "review_mitigation" 
                )

                needs_xml_resolution = (
                    api_mode == "xml" and 
                    command_type in XML_NAME_LOOKUP_REQUIRED
                )
                
                # Route to helper for XML Name-to-ID resolution
                if needs_xml_resolution:
                    # Pass all remaining arguments through to the helper command, excluding -n and the app name
                    remaining_args = []
                    i = 0
                    while i < len(command_tokens):
                        token = command_tokens[i]
                        if token in ("-n", "--app_name"):
                            # Skip -n and the app name itself
                            i += 2 
                            continue
                        
                        # Handle -t and its value if present
                        if token in ("-t", "--api_type"):
                             i += 2
                             continue
                        
                        remaining_args.append(token)
                        i += 1
                        
                    # Remove the veracli command type and add helper args
                    final_helper_args = remaining_args[1:] if remaining_args else []
                        
                    return [
                        "_HELPER_EXEC_", 
                        "app_info_ui_helper",
                        "-n", target_name_raw, 
                        "-r", region, 
                        "-t", "xml",
                        "-c", command_type
                        # Note: We currently don't pass all other arguments to the helper
                        # like -S or -b, as the helper only manages the App ID resolution
                        # but in the future, all arguments should be passed to the helper
                        # to be used in the final veracli command execution.
                    ]
                        
                # Handle REST API commands (like summary_report -t REST)
                if api_mode == "rest":
                    return [
                        "_HELPER_EXEC_", 
                        "app_info_ui_helper",
                        "-n", target_name_raw, 
                        "-r", region, 
                        "-t", "rest",
                        "-c", command_type
                    ]
        
        # If it's a direct, non-ambiguous veracli command (e.g., veracli app_info -a 1234)
        if command_tokens and command_tokens[0].lower() == "veracli":
            return command_tokens

    # 2. Setup for Command Mapping (for natural language commands)
    api_type, cleaned_query = get_api_type_and_clean_query(query)
    q = cleaned_query.lower()
    command_tokens = []
    
    target_guid = get_target_guid(query) 
    target_name = get_target_name(query, app_name)
    
    HELPER_EXEC_TOKEN = "_HELPER_EXEC_"
    
    # --- Command Mapping ---

    if "check api" in q or "api credentials" in q or "validity" in q or "creds" in q or "api cred" in q:
        command_tokens = ["api_check"]

    if "list users" in q or "all user" in q or "users" in q or "get users" in q or "all users" in q:
        command_tokens = ["api_check", "--user", "all"]    

    elif "list app" in q or "show app" in q or "applications" in q or "app list" in q or "applist" in q or "get apps" in q:
        # Check if REST listing is requested explicitly
        if api_type == "REST" or "list app rest" in q:
            command_tokens = ["app_list", "--api_type", "REST"]
        else:
            command_tokens = ["app_list", "--api_type", "XML"]

    # Route ALL REST App Info calls involving names/GUIDs to the helper for JSON/GUID management.
    if re.match(r"app_info\s+.*rest", query.lower()):
        
        if target_guid:
            # Case A: Selection/Unique GUID lookup -> Use helper with -g
            command_tokens = [HELPER_EXEC_TOKEN, "app_info_ui_helper", "-g", target_guid, "-r", region]
            
        elif target_name:
            # Case B: Initial ambiguous/unique name search -> Use helper with -n
            command_tokens = [HELPER_EXEC_TOKEN, "app_info_ui_helper", "-n", target_name, "-r", region]
            
    # Fallthrough to original app_info (only for ID or XML lookups not caught above)
    if not command_tokens and ("app info" in q or "application info" in q):
        pass

    # --- Final Token Build ---
    if command_tokens:
        if command_tokens[0] != HELPER_EXEC_TOKEN:
            if "--region" not in command_tokens:
                command_tokens.extend(["--region", region])
            
            if api_type and "--api_type" not in command_tokens and "app_list" not in command_tokens[0]:
                command_tokens.extend(["--api_type", api_type])
            
    else:
        return ["--help"]

    return command_tokens

# --- Core CLI Execution ---

def run_veracli(command_list: list[str] | str, env_overrides: Optional[Dict[str, str]] = None) -> dict[str, Any]:
    """
    Executes the command list, either a direct 'veracli' command or an internal helper script.
    """
    if isinstance(command_list, str):
        full_cmd = shlex.split(command_list)
    else:
        full_cmd = command_list
        
    HELPER_EXEC_TOKEN = "_HELPER_EXEC_"
    
    # --- Intercept Internal File Retrieval Command (NEW) ---
    if full_cmd and full_cmd[0].lower() == "retrieve_agent_file" and len(full_cmd) == 2:
        file_path = full_cmd[1]
        try:
            # Read the file content in binary mode
            with open(file_path, "rb") as f:
                content_bytes = f.read()
            
            # Base64 encode the content
            encoded_content = base64.b64encode(content_bytes).decode('utf-8')
            
            return {
                "command": full_cmd,
                "output": encoded_content,
                "stderr": "",
                "exit_code": 0,
            }
        except FileNotFoundError:
            return {
                "command": full_cmd,
                "output": "",
                "stderr": f"File not found at: {file_path}",
                "exit_code": 1,
            }
        except Exception as e:
            return {
                "command": full_cmd,
                "output": "",
                "stderr": f"Error reading file {file_path}: {str(e)}",
                "exit_code": 1,
            }
    # -----------------------------------------------------

    if full_cmd and full_cmd[0] == HELPER_EXEC_TOKEN:
        
        helper_script_name = full_cmd[1]
        helper_args = full_cmd[2:]
        
        # Adjusted pathing assuming helper script is in a known location relative to main.py
        helper_script_path = os.path.join(os.path.dirname(__file__), 
                                          "..", 
                                          "xml_api_cli", 
                                          "tasks", 
                                          f"{helper_script_name}.py")
        
        # Execute the helper script using the current Python interpreter
        full_cmd = [sys.executable, helper_script_path] + helper_args
        
    elif full_cmd and full_cmd[0].lower() != "veracli" and full_cmd[0] != "--help":
        # Prepend 'veracli' if it's a CLI command without the prefix
        full_cmd.insert(0, "veracli")
    
    try:
        # Prepare environment for subprocess: merge current env with any overrides provided
        env_for_proc = os.environ.copy()
        if env_overrides:
            # Only accept string values
            # Normalize region key: if caller provided 'REGION' or 'region', map it
            # to the library-expected env var 'VERACODE_REGION' so defaults are
            # applied correctly by xml_api_cli.config.DEFAULT_REGION.
            region_val = None
            for k, v in env_overrides.items():
                if str(k).lower() == 'region' and v:
                    region_val = str(v)
                    break

            for k, v in env_overrides.items():
                env_for_proc[str(k)] = str(v)

            if region_val and 'VERACODE_REGION' not in env_for_proc:
                env_for_proc['VERACODE_REGION'] = region_val

        proc = subprocess.Popen(
            full_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env_for_proc
        )
        stdout, stderr = proc.communicate(timeout=60)

        return {
            "command": full_cmd,
            "output": stdout,
            "stderr": stderr,
            "exit_code": proc.returncode,
        }

    except subprocess.TimeoutExpired:
        proc.kill()
        return {
            "command": full_cmd,
            "output": "",
            "stderr": "Execution timed out after 60 seconds.",
            "exit_code": -1,
        }

    except Exception as e:
        return {
            "command": full_cmd,
            "output": "",
            "stderr": f"Execution error running: {' '.join(full_cmd)}. Exception: {str(e)}",
            "exit_code": -1,
        }

# --- Main Endpoint ---

@app.post("/run")
async def query_agent(body: Query):
    nl_query = body.query

    # --- Decide whether to treat the incoming query as an already-formed CLI
    # invocation or as natural language that needs mapping via `build_command`.
    # We only bypass `build_command` when the query clearly looks like a
    # veracli CLI invocation (e.g., starts with 'veracli' or a known
    # subcommand like 'app_list', 'app_info', etc.). This avoids misclassifying
    # natural language inputs that merely contain flags (for example
    # 'list app --api_type REST').
    lower_q = nl_query.strip().lower()
    tokens = shlex.split(nl_query)
    first_token = tokens[0].lower() if tokens else ""

    KNOWN_SUBCOMMANDS = {
        'api_check', 'app_list', 'app_info', 'build_list', 'build_info',
        'detailed_report', 'summary_report', 'review_mitigation', 'app_info_ui_helper'
    }

    if lower_q.startswith("retrieve_agent_file"):
        cli_cmd_input = tokens
    elif first_token in KNOWN_SUBCOMMANDS:
        # Already a CLI-style invocation of known top-level subcommand; preserve explicit flags/values
        cli_cmd_input = tokens
    else:
        # Natural language or ambiguous input — run through build_command.
        # Extract explicit region from the query (if present) or from forwarded
        # credentials, and pass it to build_command so it doesn't default to 'us'.
        region_candidate = None
        try:
            q_tokens = tokens
            if '--region' in q_tokens:
                idx = q_tokens.index('--region')
                if idx + 1 < len(q_tokens):
                    region_candidate = q_tokens[idx + 1]
            elif '-r' in q_tokens:
                idx = q_tokens.index('-r')
                if idx + 1 < len(q_tokens):
                    region_candidate = q_tokens[idx + 1]
        except Exception:
            region_candidate = None

        # Fallback to credentials-provided region (case-insensitive) if available
        if not region_candidate and body.credentials:
            for k, v in body.credentials.items():
                if k.lower() == 'region' and v:
                    region_candidate = v.strip()
                    break

        # If the user explicitly prefixed with 'veracli', still run through
        # build_command so name-based lookups ("-n <name>") are routed to the
        # helper implementation which produces structured JSON.
        cli_cmd_input = build_command(nl_query, region=(region_candidate or "us"))

    # Normalize env_overrides: start with forwarded credentials (if any)
    env_overrides_to_pass = dict(body.credentials) if body.credentials else {}

    # If the CLI tokens include an explicit region flag, ensure the subprocess
    # environment also gets VERACODE_REGION so library defaults align.
    try:
        token_list = cli_cmd_input if isinstance(cli_cmd_input, list) else shlex.split(' '.join(cli_cmd_input))
        if '--region' in token_list:
            idx = token_list.index('--region')
            if idx + 1 < len(token_list):
                env_overrides_to_pass['REGION'] = token_list[idx + 1]
        elif '-r' in token_list:
            idx = token_list.index('-r')
            if idx + 1 < len(token_list):
                env_overrides_to_pass['REGION'] = token_list[idx + 1]
    except Exception:
        pass

    # Pass per-request credentials (if any) into the execution environment
    result = run_veracli(cli_cmd_input, env_overrides=env_overrides_to_pass)
    
    if result.get("exit_code") != 0:
        return result

    # Return the result dictionary on success
    return result