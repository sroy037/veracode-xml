import argparse
import sys
from typing import List, Dict, Any
import requests
from veracode_api_signing.plugin_requests import RequestsAuthPluginVeracodeHMAC
from xml_api_cli.config import api_base_rest

HELP_TEXT = "🧮 Fetch Flaws using Findings REST API."

# ----------------------------------------------------------------------
# Parser Setup
# ----------------------------------------------------------------------
def setup_parser(parser: argparse.ArgumentParser):
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-g", "--guid", help="Application GUID . Example: d4e5f6g7-h8i9-j0k1-l2m3-n4o5p6q7r8s9")
    group.add_argument("-n", "--app_name", help="Veracode application name. Example: verademo")

    parser.add_argument(
        "-r", "--region",
        default="us",
        choices=["us", "eu", "us_fed"],
        help="Region for Veracode platform (default: us)."
    )
    parser.add_argument(
        "-s", "--scan_type",
        default="",
        help="Filter findings by scan type (e.g., SAST, SCA, etc.)."
    )
    parser.add_argument(
        "-S", "--severity",
        type=int,
        choices=range(0, 6),
        help="Filter findings by severity (0-5)."
    )
    parser.add_argument(
        "-SG", "--severity_gte",
        type=int,
        choices=range(0, 6),
        help="Filter findings by severity (0-5). Specific and higher."
    )
    parser.add_argument(
        "-p", "--policy",
        choices=["true", "false"],
        help="Filter findings that violates policy."
    )
    parser.add_argument(
        "-o", "--other",
        choices=["true", "false"],
        help="Add more details like annotations, grace_period_expiration_date, etc."
    )
    parser.add_argument(
        "-t", "--api_type",
        choices=["XML", "REST"],
        default="REST",
        help="API type to use."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print full XML/JSON response."
    )

# ----------------------------------------------------------------------
# REST API Helper
# ----------------------------------------------------------------------
def find_app_rest_by_name(app_name: str, region: str = "us"):
    """Search apps by name using REST API (partial match supported)."""
    base_url = api_base_rest(region).rstrip("/")
    url = f"{base_url}/appsec/v1/applications/?name={app_name}"

    resp = requests.get(url, auth=RequestsAuthPluginVeracodeHMAC(), timeout=10)
    if resp.status_code != 200:
        print(f"❌ Failed to fetch applications (HTTP {resp.status_code}): {resp.text}")
        return []

    data = resp.json()
    apps = data.get("_embedded", {}).get("applications", [])
    results = []

    for app in apps:
        profile = app.get("profile", {})
        results.append({
            "id": app.get("id"),
            "guid": app.get("guid"),
            "name": profile.get("name"),
            "policy": (profile.get("policies") or [{}])[0].get("name", "-"),
            "business_unit": profile.get("business_unit", {}).get("name", "-"),
            "last_scan": app.get("last_completed_scan_date", "-"),
            "criticality": profile.get("business_criticality", "-"),
        })
    return results

# ----------------------------------------------------------------------
# Build Full URL with Query Parameters
# ----------------------------------------------------------------------
def build_full_url(base_url: str, scan_type: str = "", severity: int = None, severity_gte: int = None, policy: str = "", other: str = "") -> str:
    """Build full URL with query parameters for findings."""
    params = []
    if scan_type:
        params.append(f"scan_type={scan_type}")
    if not scan_type:
        print("📡 Scan Type filter is not provided. All scan types will be included except SCA.\n")
    if severity is not None:
        params.append(f"severity={severity}")
    if severity_gte and scan_type != "SCA":
        params.append(f"severity_gte={severity_gte}")
    elif severity_gte and scan_type == "SCA":
        print(f"⚠️ Severity_GTE filter is not applicable for SCA scan type and will be ignored. Listing for selected severity: {severity_gte}\n")
        params.append(f"severity={severity_gte}")
    if policy and scan_type != "SCA":
        params.append(f"violates_policy={policy}")
    elif policy and scan_type == "SCA":
        print("⚠️ Policy filter is not applicable for SCA scan type and will be ignored.\n")
    
    if other:
        params.append(f"include_annot={other}&include_exp_date={other}")
        print("📡 'Other' details like annotations and grace period expiration date will be included.\n")

    if params:
        return f"{base_url}?" + "&".join(params)
    return base_url


# ----------------------------------------------------------------------
# Get Latest Non-Comment Action from Annotations
# ----------------------------------------------------------------------
def get_latest_non_comment_action(annotations: List[Dict[str, Any]]) -> str:
    """
    Finds the 'action' from the latest annotation that is NOT 'COMMENT'.
    """
    if not annotations:
        return "-"

    # 1. Sort by the 'created' timestamp in descending order (latest first)
    sorted_annotations = sorted(
        annotations,
        key=lambda x: x.get('created', '0'),  # Use a default for safety
        reverse=True
    )

    # 2. Iterate through the sorted list and return the first non-COMMENT action
    for annotation in sorted_annotations:
        action = annotation.get('action')
        if action and action != "COMMENT":
            return action

    # 3. If no non-comment action is found
    return "-"

# ----------------------------------------------------------------------
# Display Findings Details
# ----------------------------------------------------------------------
def show_rest_flaw_details(data: dict, verbose: bool = False, other: str = "false", scan_type: str = ""):
    """Display flaw details from REST API response."""
    if verbose:
        import json
        print(json.dumps(data, indent=2))
        return

    flaws = data.get("_embedded", {}).get("findings", [])
    if not flaws:
        print("❌ No findings found for this application.")
        return

    headers = ["ID", "CWE", "Severity", "File Name", "Violates Policy", "Status", "First Found", "Last Seen", "Resolution", "Scan Type", "Build ID"]
    rows = []

    print(f"\n🔍 Found {len(flaws)} findings:\n")
    for flaw in flaws:
        flaw_status = flaw.get("finding_status", {})
        flaw_detail = flaw.get("finding_details", {})
        cwe = flaw_detail.get("cwe", {})
        flaw_id = flaw.get("issue_id", "-")
        build_id = flaw.get("build_id", "-")
        scan_type = flaw.get("scan_type", "-")
        severity = flaw_detail.get("severity", "-")
        cwe_id = cwe.get("id", "-")
        filename = flaw_detail.get("file_name", "-")
        if filename == "-":
            filename = flaw_detail.get("hostname", "-")
        violates_policy = flaw.get("violates_policy", False)
        status = flaw_status.get("status", "-")
        first_found_date = flaw_status.get("first_found_date", "-")
        resolution_status = flaw_status.get("resolution_status", "-")
        last_seen_date = flaw_status.get("last_seen_date", "-")
        if scan_type == "SCA":
            filename = flaw_detail.get("component_filename", "-")
            language = flaw_detail.get("language", "-")
            cve = flaw_detail.get("cve", {})
            cve_id = cve.get("name", "-")
            cve_severity = cve.get("severity", "-")
            finding_metadata = flaw_detail.get("metadata", {})
            scan_mode = finding_metadata.get("sca_scan_mode", "-")
            dep_mode = finding_metadata.get("sca_dep_mode", "-")
            licenses_info = flaw_detail.get("licenses") or []
            license = licenses_info[0] if licenses_info else {}
            license_id = license.get("license_id", "-")
        
        if other == "true":
            expiry = flaw.get("grace_period_expiration_date", "-")
            annotations = flaw.get("annotations", [])
            latest_action = get_latest_non_comment_action(annotations)
            if scan_type == "SCA":
                headers = ["License", "CVE", "Issue Sev", "CVE Sev", "Component", "Language", "Scan Mode", "Dependency Mode", "Violates Policy", "Status", "First Found", "Last Seen", "Resolution", "Grace Period Expiry", "Mitigation"]
                rows.append([license_id,cve_id,severity,cve_severity,filename,language,
                    scan_mode,dep_mode,
                    "🔴" if violates_policy else "🟢",
                    status,first_found_date,last_seen_date,resolution_status,expiry,latest_action
                ])
            else:    
                headers = ["ID", "CWE", "Severity", "File Name", "Violates Policy", "Status", "First Found", "Last Seen", "Resolution", "Grace Period Expiry", "Mitigation", "Scan Type", "Build ID"] 
                rows.append([flaw_id,cwe_id,severity,filename,
                    "🔴" if violates_policy else "🟢",
                    status,first_found_date,last_seen_date,resolution_status,expiry,latest_action,scan_type,build_id
                ])
        else:
            if scan_type == "SCA":
                headers = ["License", "CVE", "Issue Sev", "CVE Sev", "Component", "Language", "Scan Mode", "Dependency Mode", "Violates Policy", "Status", "First Found", "Last Seen", "Resolution"]
                rows.append([license_id,cve_id,severity,cve_severity,filename,language,
                    scan_mode,dep_mode,
                    "🔴" if violates_policy else "🟢",
                    status,first_found_date,last_seen_date,resolution_status
                ])
            else: 
                rows.append([flaw_id,cwe_id,severity,filename,
                    "🔴" if violates_policy else "🟢",
                    status,first_found_date,last_seen_date,resolution_status,scan_type,build_id
                ])
        

    # Print in tabular format
    col_widths = [max(len(str(row[i])) for row in rows + [headers]) + 2 for i in range(len(headers))]
    header_row = "".join(str(headers[i]).ljust(col_widths[i]) for i in range(len(headers)))
    print(header_row)
    print("-" * len(header_row))
    for row in rows:
        print("".join(str(row[i]).ljust(col_widths[i]) for i in range(len(row))))
    print("\n")


# ----------------------------------------------------------------------
# Main Run
# ----------------------------------------------------------------------
def run(args):
    try:
        if args.guid:
            guid = args.guid
        elif not args.app_name and not args.guid:
            print("❌ Please enter a valid GUID or Application name to fetch flaw list.")
            sys.exit(0)

        if args.app_name and not args.guid:
            print(f"📡 Searching applications matching '{args.app_name}' via REST API...")
            matches = find_app_rest_by_name(args.app_name, args.region)
            if not matches:
                print("❌ No applications found.")
                sys.exit(0)

            if len(matches) == 1:
                guid = matches[0]["guid"]
            else:
                print("\n⚠️ Multiple matches found:")
                for i, app in enumerate(matches, 1):
                    last_scan = app.get("last_scan", "-")
                    print(f"  [{i}] {app['name']:<35}  (ID: {app['id']})  Last Scan: {last_scan}")
                while True:
                    choice = input("Enter the number of the app to Pull Flaw List: ").strip()
                    if choice.isdigit() and 1 <= int(choice) <= len(matches):
                        guid = matches[int(choice)-1]["guid"]
                        app_name = matches[int(choice)-1]["name"]
                        break
                    print("Invalid selection. Try again.")

        # Fetch Findings details
        base_url = api_base_rest(args.region).rstrip("/")
        detail_url = f"{base_url}/appsec/v2/applications/{guid}/findings"
        final_url = build_full_url(detail_url, args.scan_type, args.severity, args.severity_gte, args.policy, args.other)
        params = {"size": 300, "page": 0}
        total_flaws = []
        while True:
            #print(f"📡 Fetching findings from: {final_url} (Page {params['page'] + 1}) ")
            resp = requests.get(final_url, params=params, auth=RequestsAuthPluginVeracodeHMAC(), timeout=20)
            if resp.status_code != 200:
                print(f"⚠️  Failed to fetch findings (HTTP {resp.status_code}): {resp.text}")
                break

            data = resp.json()
            findings = data.get("_embedded", {}).get("findings", [])
            if not findings:
                break
            total_flaws.extend(findings)

            # 🧾 Pagination info
            page_info = data.get("page", {})
            current_page = page_info.get("number", 0)
            total_pages = page_info.get("total_pages", 1)

            #print(f"📄 Processed page {current_page + 1}/{total_pages} ({len(findings)} findings)")

            # Exit if this was the last page
            if current_page >= total_pages - 1:
                break

            params["page"] = current_page + 1  # move to next page
        
        if total_flaws:
            data = {"_embedded": {"findings": total_flaws}}
            show_rest_flaw_details(data, args.verbose, args.other, args.scan_type)
        else:
            print("❌ No findings found for this application with the provided parameters.")

    except KeyboardInterrupt:
        print("\n🛑 Operation cancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)