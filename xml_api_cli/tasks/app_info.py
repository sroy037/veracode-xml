"""
Fetch information for a specific application.
Reference: https://docs.veracode.com/r/r_getappinfo
"""

import argparse
import sys
import os
import requests
import xml.etree.ElementTree as ET
from veracode_api_signing.plugin_requests import RequestsAuthPluginVeracodeHMAC
from xml_api_cli.utils.api_helpers import find_app_by_name, pretty_print_xml
from xml_api_cli.config import xml_api_v5_base

HELP_TEXT = "🧾 Fetch detailed info for a specific Veracode application by app_id or app_name."

def setup_parser(parser: argparse.ArgumentParser):
    """
    Setup argparse for this task. Either --app_id or --app_name must be provided.
    """
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-a", "--app_id",
        help="Application ID (integer). Alternate to --app_name. Example: 2477056"
    )
    group.add_argument(
        "-n", "--app_name",
        help="Veracode application name. Alternate to --app_id. Example: verademo"
    )
    parser.add_argument(
        "-r", "--region",
        default="us",
        choices=["us", "eu", "us_fed"],
        help="Region for Veracode platform (default: us)."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print full XML response."
    )

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
    """
    Run the app_info task.
    Resolves app_id from app_name if necessary, fetches XML, prints and saves.
    """
    try:
        # Resolve app_id from app_name if needed
        if not args.app_id and args.app_name:
            print(f"🔍 Searching for application matching name: '{args.app_name}' ...")
            app_id = find_app_id_by_name(args.app_name, args.region)
            if not app_id:
                print("❌ No matching applications found.")
                sys.exit(1)
            args.app_id = app_id

        if not args.app_id:
            print("❌ Either --app_id or --app_name must be provided.")
            sys.exit(1)

        print(f"📡 Fetching app info for app_id={args.app_id} ...")

        url = xml_api_v5_base(args.region) + "getappinfo.do"
        response = requests.get(
            url,
            params={"app_id": args.app_id},
            auth=RequestsAuthPluginVeracodeHMAC()
        )

        if response.status_code != 200:
            print(f"❌ API request failed ({response.status_code}): {response.text}")
            sys.exit(1)

        content = response.text
        if args.verbose:
            pretty_print_xml(content)

        # Parse XML to confirm presence of <application>
        ns = {"ns": "https://analysiscenter.veracode.com/schema/2.0/appinfo"}
        root = ET.fromstring(content)
        app_elem = root.find("ns:application", ns)
        if app_elem is None:
            print("⚠️  No <application> element found — response may be malformed.")
        else:
            print("\n✅ Application Info:")
            for key in ["app_id", "app_name", "business_criticality", "policy",
                        "policy_updated_date", "teams", "business_unit", "modified_date"]:
                print(f"  {key:22} : {app_elem.attrib.get(key, '-') or '-'}")

            # Optional: custom fields
            custom_fields = app_elem.findall("ns:customfield", ns)
            if custom_fields:
                print("\n🧩 Custom Fields:")
                for cf in custom_fields:
                    print(f"  {cf.attrib.get('name','-')}: {cf.attrib.get('value','-') or '-'}")

    except KeyboardInterrupt:
        print("\n🛑 Operation cancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
