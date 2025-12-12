import argparse
import sys
import requests
import xml.etree.ElementTree as ET
from veracode_api_signing.plugin_requests import RequestsAuthPluginVeracodeHMAC
from xml_api_cli.utils.api_helpers import find_app_by_name, pretty_print_xml
from xml_api_cli.config import xml_api_v5_base, api_base_rest

HELP_TEXT = "🧾 Fetch detailed info for a specific Veracode application by app_id or app_name (XML or REST)."

# ----------------------------------------------------------------------
# Parser Setup
# ----------------------------------------------------------------------
def setup_parser(parser: argparse.ArgumentParser):
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-a", "--app_id", help="Application ID (integer). Example: 2477056")
    group.add_argument("-n", "--app_name", help="Veracode application name. Example: verademo")

    parser.add_argument(
        "-r", "--region",
        default="us",
        choices=["us", "eu", "us_fed"],
        help="Region for Veracode platform (default: us)."
    )
    parser.add_argument(
        "-t", "--api_type",
        default="XML",
        choices=["XML", "REST"],
        help="API type to use (default: XML)."
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
# Display REST App Details
# ----------------------------------------------------------------------
def show_rest_app_details(app, verbose=False):
    profile = app.get("profile", {})
    print("\n✅ Application Info (REST):")
    print(f"  ID:                   {app.get('id')}")
    print(f"  GUID:                 {app.get('guid')}")
    print(f"  Name:                 {profile.get('name')}")
    print(f"  Business Unit:        {profile.get('business_unit', {}).get('name', '-')}")
    print(f"  Business Criticality: {profile.get('business_criticality', '-')}")
    print(f"  Last Modified:        {app.get('modified')}")
    print(f"  Last Scan:            {app.get('last_completed_scan_date', '-')}")
    print(f"  Policy:               {(profile.get('policies') or [{}])[0].get('name', '-')}")
    print(f"  Policy Status:        {(profile.get('policies') or [{}])[0].get('policy_compliance_status', '-')}")
    print(f"  Policy Check Date:    {app.get('last_policy_compliance_check_date')}")
    print(f"  Created:              {app.get('created')}")
    print(f"  Results URL:          {app.get('results_url', '-')}")
    teams = profile.get("teams", [])
    if teams:
        print(f"\n👥 Teams ({len(teams)}):")
        for t in teams:
            print(f"   • {t.get('team_name')} ({t.get('relationship', {}).get('display_name', '')})")
    else:
        print(f"\n👥 No Team Restriction.")

    if verbose:
        import json
        print("\n--- Full JSON Response ---")
        print(json.dumps(app, indent=2))

# ----------------------------------------------------------------------
# XML Logic
# ----------------------------------------------------------------------
def fetch_app_info_xml(app_id: str, region: str, verbose=False):
    print(f"📡 Fetching app info for app_id={app_id} (XML)...")
    url = xml_api_v5_base(region) + "getappinfo.do"
    resp = requests.get(url, params={"app_id": app_id}, auth=RequestsAuthPluginVeracodeHMAC())
    if resp.status_code != 200:
        print(f"❌ Failed to fetch app info ({resp.status_code}): {resp.text}")
        sys.exit(1)

    if verbose:
        pretty_print_xml(resp.text)

    ns = {"ns": "https://analysiscenter.veracode.com/schema/2.0/appinfo"}
    root = ET.fromstring(resp.text)
    app_elem = root.find("ns:application", ns)
    if app_elem is None:
        print("⚠️  No <application> element found.")
        return

    print("\n✅ Application Info (XML):")
    for key in ["app_id", "app_name", "business_criticality", "policy", "policy_updated_date",
                "teams", "business_unit", "modified_date"]:
        print(f"  {key:22}: {app_elem.attrib.get(key, '-')}")

# ----------------------------------------------------------------------
# Main Run
# ----------------------------------------------------------------------
def run(args):
    try:
        # --- REST MODE ---
        if args.api_type == "REST":
            if args.app_id:
                print("⚠️  The --app_id parameter is not supported for REST API. Please use --app_name instead.")
                sys.exit(1)
            if not args.app_name:
                print("❌ REST API requires --app_name to search applications.")
                sys.exit(0)

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
                    choice = input("Enter the number of the app to view details: ").strip()
                    if choice.isdigit() and 1 <= int(choice) <= len(matches):
                        guid = matches[int(choice) - 1]["guid"]
                        break
                    print("Invalid selection. Try again.")

            # Fetch REST details
            base_url = api_base_rest(args.region).rstrip("/")
            detail_url = f"{base_url}/appsec/v1/applications/{guid}"
            resp = requests.get(detail_url, auth=RequestsAuthPluginVeracodeHMAC())
            if resp.status_code == 200:
                show_rest_app_details(resp.json(), args.verbose)
            else:
                print(f"❌ Failed to fetch app details ({resp.status_code}): {resp.text}")
            return

        # --- XML MODE ---
        if not args.app_id and args.app_name:
            print(f"🔍 Searching for application matching '{args.app_name}' (XML)...")
            app_list = find_app_by_name(args.app_name, args.region)
            if not app_list:
                print("❌ No matching apps found.")
                sys.exit(0)

            if isinstance(app_list, list):
                if len(app_list) == 1:
                    args.app_id = app_list[0]["app_id"]
                else:
                    print("\n⚠️ Multiple matches found:")
                    for i, app in enumerate(app_list, 1):
                        last_update = app.get("last_policy_update", "-")
                        print(f"  [{i}] {app['app_name']:<35} (App ID: {app['app_id']})  Last Policy Update: {last_update}")
                    while True:
                        choice = input("Enter the number of the app to view details: ").strip()
                        if choice.isdigit() and 1 <= int(choice) <= len(app_list):
                            args.app_id = app_list[int(choice) - 1]["app_id"]
                            break
                        print("Invalid selection. Try again.")
            else:
                args.app_id = app_list

        if not args.app_id:
            print("❌ Either --app_id or --app_name must be provided for XML mode.")
            sys.exit(0)

        fetch_app_info_xml(args.app_id, args.region, args.verbose)

    except KeyboardInterrupt:
        print("\n🛑 Operation cancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)