"""
List all applications in the Veracode account (XML or REST).
Reference:
  XML  - https://docs.veracode.com/r/r_getapplist
  REST - https://docs.veracode.com/r/c_appsec_get_apps
"""

import xml.etree.ElementTree as ET
import requests
from veracode_api_signing.plugin_requests import RequestsAuthPluginVeracodeHMAC
from xml_api_cli.config import endpoint_getapplist, api_base_rest
from datetime import datetime

HELP_TEXT = "🧰 Fetch list of all applications in your Veracode account (XML or REST)."

# ----------------------------------------------------------------------
# Argument setup
# ----------------------------------------------------------------------
def setup_parser(parser):
    parser.add_argument(
        "-r", "--region",
        default="us",
        choices=["us", "eu", "us_fed"],
        help="Veracode region (default: us)"
    )
    parser.add_argument(
        "-t", "--api_type",
        default="XML",
        choices=["XML", "REST"],
        help="API type to use: XML (legacy) or REST (modern)."
    )

# ----------------------------------------------------------------------
# REST version with pagination
# ----------------------------------------------------------------------
def list_applications_rest(region: str):
    """
    Paginated REST API call to list all applications.
    """
    base_url = api_base_rest(region).rstrip("/")
    url = f"{base_url}/appsec/v1/applications"
    page = 0
    size = 50
    all_apps = []

    print(f"📡 Fetching applications via REST API ({region})...")

    while True:
        params = {"page": page, "size": size}
        resp = requests.get(url, params=params, auth=RequestsAuthPluginVeracodeHMAC(), timeout=15)
        if resp.status_code != 200:
            print(f"❌ API request failed (HTTP {resp.status_code}): {resp.text}")
            break

        data = resp.json()
        apps = data.get("_embedded", {}).get("applications", [])
        if not apps:
            break

        all_apps.extend(apps)
        page_info = data.get("page", {})
        total_pages = page_info.get("total_pages", 1)
        current_page = page_info.get("number", 0)

        print(f"📄 Page {current_page + 1}/{total_pages} retrieved ({len(apps)} apps).")

        if current_page + 1 >= total_pages:
            break
        page += 1

    if not all_apps:
        print("⚠️  No applications found.")
        return

    # Prepare tabular output
    headers = ["App Name", "App ID", "Business Unit", "Last Scan", "Policy", "Compliance"]
    rows = []
    for app in all_apps:
        prof = app.get("profile", {})
        policy = (prof.get("policies") or [{}])[0]
        rows.append([
            prof.get("name", "N/A"),
            app.get("id", "N/A"),
            prof.get("business_unit", {}).get("name", "N/A"),
            app.get("last_completed_scan_date", "N/A"),
            policy.get("name", "N/A"),
            policy.get("policy_compliance_status", "N/A"),
        ])

    # Compute column widths
    col_widths = [max(len(str(row[i])) for row in ([headers] + rows)) for i in range(len(headers))]

    print("\n" + " | ".join(headers[i].ljust(col_widths[i]) for i in range(len(headers))))
    print("-" * (sum(col_widths) + (3 * (len(headers) - 1))))

    for row in rows:
        print(" | ".join(str(row[i]).ljust(col_widths[i]) for i in range(len(headers))))

    print(f"\n✅ Retrieved total {len(all_apps)} applications via REST API.\n")

# ----------------------------------------------------------------------
# XML version (legacy)
# ----------------------------------------------------------------------
def list_applications_xml(region: str):
    """
    Fetch applications using legacy XML API.
    """
    url = endpoint_getapplist(region)
    print(f"📡 Fetching application list from {url} ...")

    resp = requests.get(url, auth=RequestsAuthPluginVeracodeHMAC(), timeout=15)
    if resp.status_code != 200:
        print(f"❌ API request failed: {resp.status_code}")
        print(resp.text)
        return

    try:
        root = ET.fromstring(resp.text)
        ns = {"ns": root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}
        apps = root.findall(".//ns:app", ns) or root.findall(".//app")
        if not apps:
            print("⚠️  No applications found.")
            return

        print(f"✅ Found {len(apps)} applications:\n")
        for app in apps:
            app_id = app.attrib.get("app_id")
            name = app.attrib.get("app_name")
            policy_upd = app.attrib.get("policy_updated_date", "N/A")
            print(f"• {name:<35}\tID: {app_id:<8}\tLast Policy Check: {policy_upd}")

    except ET.ParseError as e:
        print(f"❌ Failed to parse XML: {e}")

# ----------------------------------------------------------------------
# Main runner
# ----------------------------------------------------------------------
def run(args):
    if args.api_type == "REST":
        list_applications_rest(args.region)
    else:
        list_applications_xml(args.region)