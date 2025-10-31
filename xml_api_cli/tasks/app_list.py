"""
List all applications in the Veracode account.
Reference: https://docs.veracode.com/r/r_getapplist
"""

import xml.etree.ElementTree as ET
import requests
from veracode_api_signing.plugin_requests import RequestsAuthPluginVeracodeHMAC
from xml_api_cli.config import endpoint_getapplist

HELP_TEXT = "ℹ️ Fetch list of all applications in your Veracode account."

def setup_parser(parser):
    parser.add_argument(
        "-r", "--region", default="us", help="Veracode region (us, eu, us_fed)"
    )

def run(args):
    url = endpoint_getapplist(args.region)
    print(f"📡 Fetching application list from {url} ...")

    response = requests.get(url, auth=RequestsAuthPluginVeracodeHMAC())
    if response.status_code != 200:
        print(f"❌ API request failed: {response.status_code}")
        print(response.text)
        return

    # Parse XML safely (handle namespace)
    try:
        root = ET.fromstring(response.text)
        ns = {"ns": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}

        apps = root.findall(".//ns:app", ns) or root.findall(".//app")
        if not apps:
            print("⚠️  No applications found.")
            return

        print(f"✅ Found {len(apps)} applications:\n")
        for app in apps:
            app_id = app.attrib.get("app_id")
            name = app.attrib.get("app_name")
            policy_upd = app.attrib.get("policy_updated_date")
            print(f"• {name:<35}\tID: {app_id:<8}\tLast Policy Check: {policy_upd}")

    except ET.ParseError as e:
        print(f"❌ Failed to parse XML: {e}")
