"""
List all builds under a given application.
Reference: https://docs.veracode.com/r/r_getbuildlist
"""

import xml.etree.ElementTree as ET
import requests
import sys
from veracode_api_signing.plugin_requests import RequestsAuthPluginVeracodeHMAC
from xml_api_cli.config import endpoint_getbuildlist, endpoint_getapplist
from xml_api_cli.utils.api_helpers import find_app_by_name

HELP_TEXT = "📜 List all builds under a specific application."

def setup_parser(parser):
    parser.add_argument("-a", "--app_id", help="Veracode application ID (alternate to --app_name)")
    parser.add_argument("-n", "--app_name", help="Veracode application name (alternate to --app_id)")
    parser.add_argument("-r", "--region", default="us", help="Veracode region (us, eu, us_fed)")

def find_app_id_by_name(app_name: str, region: str = "us") -> str | None:
    """
    Find an app_id given a full or partial app name.
    Prompts the user if multiple matches are found.
    """
    apps = find_app_by_name(app_name, region)
    if not apps:
        return None

    if len(apps) == 1:
        app = apps[0]
        print(f"✅ Found application: {app['app_name']}\t(ID: {app['app_id']})\t(Last Policy Check: {app['last_policy_update']})")
        return app["app_id"]

    # Multiple matches found
    print("\n⚠️  Multiple matches found:")
    for i, app in enumerate(apps, 1):
        print(f"  [{i:<2}] {app['app_name']:<30}\t(ID: {app['app_id']})\t(Last Policy Check: {app['last_policy_update']})")

    while True:
        choice = input("Enter the number of the application you want to use: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(apps):
            selected = apps[int(choice) - 1]
            print(f"✅ Selected: {selected['app_name']} (ID: {selected['app_id']})")
            return selected["app_id"]
        print("Invalid choice. Please try again.")


def run(args):
    # Resolve app_id from name if needed
    app_id = args.app_id
    if not app_id and args.app_name:
        print(f"Resolving app_id for app_name='{args.app_name}' ...")
        app_id = find_app_id_by_name(args.app_name, args.region)
        if not app_id:
            print(f"❌ App name '{args.app_name}' not found in your Veracode account.")
            return

    if not app_id:
        print("❌ Please provide --app_id or --app_name.")
        return

    url = endpoint_getbuildlist(args.region) + f"?app_id={app_id}"
    print(f"📡 Fetching builds for app_id={app_id} ...")

    response = requests.get(url, auth=RequestsAuthPluginVeracodeHMAC())
    if response.status_code != 200:
        print(f"❌ API request failed: {response.status_code}")
        print(response.text)
        return

    try:
        root = ET.fromstring(response.text)
        ns = {"ns": root.tag.split('}')[0].strip('{')} if "}" in root.tag else {}
        builds = root.findall(".//ns:build", ns) if ns else root.findall(".//build")

        if not builds:
            print("⚠️  No builds found for this app.")
            return

        print(f"✅ Found {len(builds)} builds:\n")
        for b in builds:
            print(
                f"• Build ID: {b.attrib.get('build_id')}, "
                f"Version: {b.attrib.get('version')}, "
                f"Scan Type: {'Dynamic' if b.attrib.get('dynamic_scan_type') else 'Static'}, "
                f"Last Policy Update: {b.attrib.get('policy_updated_date', 'N/A')}"
            )

    except ET.ParseError as e:
        print(f"❌ Failed to parse XML: {e}")
