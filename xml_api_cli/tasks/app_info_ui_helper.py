import argparse
import sys
import json
import requests
import subprocess
import re
from veracode_api_signing.plugin_requests import RequestsAuthPluginVeracodeHMAC
# Note: Assuming xml_api_cli.config is a module you have in your environment
# and correctly defines api_base_rest and endpoint_getapplist.
from xml_api_cli.config import api_base_rest, endpoint_getapplist 
import xml.etree.ElementTree as ET # For XML parsing

HELP_TEXT = "🔍 [UI Helper] Fetches App Info REST/XML matches (JSON output) or retrieves details by GUID/ID (CLI output)."

# --- API Utility Function ---
def _make_api_request(url: str, method: str = "GET", timeout: int = 10):
    """
    Centralized function for making authenticated API requests and handling common errors.
    Returns: requests.Response object or raises requests.exceptions.RequestException.
    """
    try:
        if method == "GET":
            resp = requests.get(url, auth=RequestsAuthPluginVeracodeHMAC(), timeout=timeout)
        else:
            # Placeholder for other methods if needed later (e.g., POST)
            raise ValueError(f"Unsupported HTTP method: {method}")

        resp.raise_for_status()
        return resp
    except requests.exceptions.RequestException as e:
        # Re-raise the exception to be handled by the caller with specific context
        raise requests.exceptions.RequestException(f"API Request Failed (URL: {url}): {e}")

# --- XML API Helper ---
def find_app_xml_by_name(app_name: str, region: str = "us"):
    """
    Search apps by name using XML API. This function fetches the full app list 
    and filters the results locally by name (case-insensitive partial match).
    """
    
    url = endpoint_getapplist(region)

    try:
        # Use the centralized utility
        resp = _make_api_request(url, timeout=20) 
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": f"XML API Request Failed: {e}"}

    try:
        root = ET.fromstring(resp.text)
        
        # Extract the default namespace from the root tag and define a prefix 'ns'.
        ns_url = root.tag.split('}')[0].strip('{')
        ns = {"ns": ns_url}
        
        # Use the namespace-aware XPath to find the 'app' elements.
        apps_elements = root.findall(".//ns:app", ns)
        
        all_apps = []
        for app_element in apps_elements:
            app_id = app_element.get("app_id")
            # CRUCIAL: Ensure app_id exists as it is required for XML CLI tasks.
            if not app_id:
                print(f"⚠️ App named '{app_element.get('app_name')}' found but missing required 'app_id' in XML response. Skipping.", file=sys.stderr)
                continue
                
            all_apps.append({
                "id": app_id, 
                "name": app_element.get("app_name"),
                "guid": app_element.get("guid", "-"),
                "last_scan": app_element.get("policy_updated_date", "-"), 
                "api_type": "xml"
            })
    
    except ET.ParseError as e:
        return {"status": "error", "message": f"Failed to parse XML response from {url}: {e}"}
    except Exception as e:
        return {"status": "error", "message": f"Unknown error during XML parsing: {e}"}

    # Implement local filtering (the "grep" logic)
    search_term = app_name.lower()
    
    # Filter and add index numbers only to matching apps
    filtered_apps = []
    for app in all_apps:
        if search_term in app['name'].lower(): 
            app['index'] = len(filtered_apps) + 1 
            filtered_apps.append(app)

    return {"status": "success", "matches": filtered_apps}

# --- REST API Helper ---
def find_app_rest_by_name(app_name: str, region: str = "us"):
    """Search apps by name using REST API (partial match supported)."""
    base_url = api_base_rest(region).rstrip("/")
    url = f"{base_url}/appsec/v1/applications/?name={app_name}" 

    try:
        # Use the centralized utility
        resp = _make_api_request(url)
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": f"REST API Request Failed: {e}"}

    data = resp.json()
    apps = data.get("_embedded", {}).get("applications", [])
    
    results = []
    for i, app in enumerate(apps):
        profile = app.get("profile", {})
        results.append({
            "index": i + 1,
            "id": app.get("id"),
            "name": profile.get("name"),
            "guid": app.get("guid"),
            "last_scan": app.get("last_completed_scan_date", "-"),
            "api_type": "rest"
        })
        
    return {"status": "success", "matches": results}

# --- Conceptual Output Formatting (Called when -g is used for REST) ---
def show_rest_app_details(app_data: dict, verbose: bool):
    """Formats and prints the final REST app details as CLI output (plain text)."""
    profile = app_data.get('profile', {})
    
    # Safely extract policy information
    policy_data = (profile.get('policies') or [{}])[0]

    # Print the plain text output that the Agent will capture
    print("\n--- Veracode Application Details (REST) ---")
    print(f"  ID:                   {app_data.get('id')}")
    print(f"  GUID:                 {app_data.get('guid')}")
    print(f"  Name:                 {profile.get('name')}")
    print(f"  Business Unit:        {profile.get('business_unit', {}).get('name', '-')}")
    print(f"  Business Criticality: {profile.get('business_criticality', '-')}")
    print(f"  Last Modified:        {app_data.get('modified')}")
    print(f"  Last Scan:            {app_data.get('last_completed_scan_date', '-')}")
    print(f"  Policy:               {policy_data.get('name', '-')}")
    print(f"  Policy Status:        {policy_data.get('policy_compliance_status', '-')}")
    print(f"  Policy Check Date:    {app_data.get('last_policy_compliance_check_date')}")
    print(f"  Created:              {app_data.get('created')}")
    print(f"  Results URL:          {app_data.get('results_url', '-')}")
    
    if verbose:
        print("\n--- Raw Profile Details ---")
        print(json.dumps(profile, indent=2))
    print("------------------------------------------\n")

# ----------------------------------------------------------------------
# Parser Setup (Updated for XML and final command)
# ----------------------------------------------------------------------
def setup_parser(parser: argparse.ArgumentParser):
    """Sets up the argument parser for the UI helper."""
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-n", "--app_name",
        help="Veracode application name (for search/list)."
    )
    group.add_argument(
        "-g", "--guid",
        help="Application GUID (for specific REST details lookup)."
    )
    # Argument for App ID lookup (for XML commands)
    group.add_argument(
        "-a", "--app_id",
        help="Application ID (for specific XML details lookup)."
    )
    
    parser.add_argument(
        "-r", "--region",
        default="us",
        choices=["us", "eu", "us_fed"],
        help="Region for Veracode platform (default: us)."
    )
    # Argument for API Type and Command Type
    parser.add_argument(
        "-t", "--api_type",
        choices=["rest", "xml"],
        default="rest",
        help="API type to use for the lookup."
    )
    parser.add_argument(
        "-c", "--command",
        help="The final CLI command to execute after selection (e.g., build_list, app_info, review_mitigation)."
    )
    # NEW ARGUMENT: Original command arguments to preserve other flags (-S, -f, etc.)
    parser.add_argument(
        "--original_args_json",
        default="[]",
        help="JSON string of the original command tokens (excluding 'veracli') to reconstruct the final command."
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output for details lookup."
    )

# ----------------------------------------------------------------------
# Main Run (Handles REST search, GUID fetch, XML search, and XML execution)
# ----------------------------------------------------------------------
def run(args):
    
    # --- Case 1: Final Lookup/Execution (GUID for REST, APP_ID for XML) ---
    if args.guid or args.app_id:
        
        if args.api_type == "rest" and args.guid:
            # 1a. REST GUID Detail Fetch
            guid = args.guid
            base_url = api_base_rest(args.region).rstrip("/")
            detail_url = f"{base_url}/appsec/v1/applications/{guid}"
            
            try:
                # Use the centralized utility
                resp = _make_api_request(detail_url)
                show_rest_app_details(resp.json(), args.verbose)
            except Exception as e:
                print(f"❌ Failed to fetch REST app details: {e}", file=sys.stderr); sys.exit(1)
            
        elif args.api_type == "xml" and args.app_id and args.command:
            # 1b. XML App ID Execution
            app_id = args.app_id
            command = args.command
            
            try:
                original_args = json.loads(args.original_args_json)
            except json.JSONDecodeError:
                print(f"❌ Failed to decode original arguments JSON: {args.original_args_json}", file=sys.stderr); sys.exit(1)

            # Reconstruct the final command
            final_cmd_tokens = ["veracli"]
            
            # --- Command Reconstruction Logic ---
            name_flags = ("-n", "--app_name")
            id_flags = ("-a", "--app_id", "-i") # Added -i as a possible ID flag to look for and avoid conflicts
            issue_flags = ("-i", "--issue_ids")
            
            # 1. Substitute -n with -i and skip the app name value
            skip_next = False
            has_issue_id_flag = False
            
            for token in original_args:
                if skip_next:
                    skip_next = False
                    continue
                
                if token in name_flags:
                    # Replace the app name flag/value with the resolved App ID
                    # Use -i for build_list/build_info as that's the expected flag for App ID
                    final_cmd_tokens.extend(["-i", app_id]) 
                    skip_next = True # Skip the application name value
                else:
                    final_cmd_tokens.append(token)
                    if token in issue_flags:
                        has_issue_id_flag = True

            # 2. Add region if not present 
            if "-r" not in final_cmd_tokens and "--region" not in final_cmd_tokens:
                final_cmd_tokens.extend(["-r", args.region])
            
            # 3. FIX: Prevent interactive prompt for 'review_mitigation' if no issue ID is provided
            if command == "review_mitigation" and not has_issue_id_flag:
                # Inject a dummy issue ID (e.g., 1) to force non-interactive execution.
                final_cmd_tokens.extend(["--issue_ids", "1"])
                print("⚠️ No issue ID (-i/--issue_ids) provided for review_mitigation. Injecting '--issue_ids 1' to prevent interactive mode.", file=sys.stderr)

            
            # Execute the final command via subprocess
            try:
                proc = subprocess.run(
                    final_cmd_tokens, 
                    capture_output=True, 
                    text=True, 
                    check=True, # Raise exception for non-zero exit code
                    timeout=60
                )
                # Print output from the actual veracli command
                print(proc.stdout)
                if proc.stderr:
                    # Print stderr to the console (not redirected to stdout)
                    print(f"\n--- STDERR ---\n{proc.stderr}", file=sys.stderr)
                    
            except subprocess.CalledProcessError as e:
                print(f"\n❌ Final XML command failed (Exit Code: {e.returncode}).", file=sys.stderr)
                print(f"--- Command Output ---\n{e.stdout}", file=sys.stderr)
                print(f"--- Command Error ---\n{e.stderr}", file=sys.stderr)
                sys.exit(e.returncode)
            except subprocess.TimeoutExpired:
                print("❌ Final XML command timed out.", file=sys.stderr)
                sys.exit(1)
            except FileNotFoundError:
                print("❌ 'veracli' command not found. Check your environment PATH.", file=sys.stderr)
                sys.exit(1)

        return # Exit after successful detail fetch/execution

    # --- Case 2: App Name provided (Search/List for UI) ---
    app_name = args.app_name
    
    if args.api_type == "rest":
        results = find_app_rest_by_name(app_name, args.region)
    elif args.api_type == "xml":
        # Calls the function which fetches full list and filters locally
        results = find_app_xml_by_name(app_name, args.region)
    else:
        # This case should be impossible due to argparse choices, but included for robustness
        print(json.dumps({"status": "error", "message": "Invalid API type."}), file=sys.stderr); sys.exit(1)
    
    if results.get("status") == "error":
        print(json.dumps(results))
        sys.exit(1)
        
    matches = results.get("matches", [])
    
    # Handle single, multiple, and no matches (JSON output)
    if not matches:
        print(json.dumps({"status": "no_match", "app_name": app_name}))
    elif len(matches) == 1:
        app = matches[0]
        app_id = app["id"] # Get the resolved App ID

        # Prepare base unique result dictionary
        unique_result = {
            "status": "unique", 
            "app_id": app_id, 
            "app_name": app["name"],
            "guid": app["guid"],
            "api_type": args.api_type, 
        }
        
        # Prepare data for XML execution flow. 
        if args.api_type == "xml":
            # 🛑 CRITICAL FIX: Ensure 'app_id' is explicitly included in the context 
            # for the upstream consuming script (server.py) to find.
            unique_result.update({
                "command": args.command, 
                "original_args_json": args.original_args_json,
                "app_id": app_id 
            })

        print(json.dumps(unique_result))
    else:
        # Multiple matches found (JSON output)
        print(json.dumps({
            "status": "multiple", 
            "matches": matches, 
            "app_name": app_name,
            "api_type": args.api_type, 
            "command": args.command,
            "original_args_json": args.original_args_json
        }))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=HELP_TEXT)
    setup_parser(parser)
    args = parser.parse_args()
    run(args)