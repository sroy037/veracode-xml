"""
Fetch detailed build information.
Reference: https://docs.veracode.com/r/r_getbuildinfo
If build_id is not given, fetches the latest build (based on scan_type).
"""

import xml.etree.ElementTree as ET
import requests
import sys
from veracode_api_signing.plugin_requests import RequestsAuthPluginVeracodeHMAC
from xml_api_cli.config import endpoint_getbuildinfo, endpoint_getbuildlist, endpoint_getapplist
from xml_api_cli.utils.api_helpers import find_app_by_name

HELP_TEXT = "🧩 Fetch info for a specific or latest build."

def setup_parser(parser):
    parser.add_argument("-i", "--app_id", help="Veracode application ID")
    parser.add_argument("-n", "--app_name", help="Veracode application name (alternate to --app_id)")
    parser.add_argument("-b", "--build_id", help="Specific build ID (optional)")
    parser.add_argument(
        "-s", "--scan_type", choices=["ss", "ds"], default="ss",
        help="Scan type: ss=Static, ds=Dynamic (used if build_id not given)"
    )
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
    # Ensure we have an app_id (resolve from name if needed)
    app_id = args.app_id
    if not app_id and args.app_name:
        print(f"Resolving app_id for app_name='{args.app_name}' ...")
        app_id = find_app_id_by_name(args.app_name, args.region)
        if not app_id:
            print(f"❌ App name '{args.app_name}' not found in your Veracode account.")
            return

    if not app_id:
        print("❌ Please provide --app_id or --app_name (or provide --build_id together with --app_id).")
        return

    build_id = args.build_id
    if not build_id:
        # Fetch build list and choose latest matching scan_type
        list_url = endpoint_getbuildlist(args.region) + f"?app_id={app_id}"
        print("ℹ️  No build_id provided, fetching latest build list...")
        resp = requests.get(list_url, auth=RequestsAuthPluginVeracodeHMAC())
        if resp.status_code != 200:
            print(f"❌ Failed to fetch build list: HTTP {resp.status_code}")
            print(resp.text)
            return

        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError as e:
            print(f"❌ Failed to parse build list XML: {e}")
            return

        ns = {"ns": root.tag.split('}')[0].strip('{')} if "}" in root.tag else {}
        builds = root.findall(".//ns:build", ns) if ns else root.findall(".//build")

        if not builds:
            print("⚠️  No builds found for this app.")
            return

        # Filter for desired scan type
        if args.scan_type == "ds":
            filtered = [b for b in builds if b.attrib.get("dynamic_scan_type") == "ds" and b.attrib.get("policy_updated_date")]
        else:
            # static: dynamic_scan_type may be absent or not 'ds'
            filtered = [b for b in builds if b.attrib.get("dynamic_scan_type") not in ("ds",) ]

        if not filtered:
            print(f"⚠️  No builds found for scan_type={args.scan_type.upper()}.")
            return

        # pick latest by policy_updated_date if present, else last
        try:
            latest = max(filtered, key=lambda x: x.attrib.get("policy_updated_date", ""))
        except Exception:
            latest = filtered[-1]
        build_id = latest.attrib.get("build_id")
        print(f"✅ Using latest build_id={build_id} (scan_type={args.scan_type})")

    # Now fetch buildinfo
    url = endpoint_getbuildinfo(args.region) + f"?app_id={app_id}&build_id={build_id}"
    print(f"📡 Fetching build info for build_id={build_id} ...")
    resp = requests.get(url, auth=RequestsAuthPluginVeracodeHMAC())
    if resp.status_code != 200:
        print(f"❌ API request failed: {resp.status_code}")
        print(resp.text)
        return

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as e:
        print(f"❌ Failed to parse build info XML: {e}")
        return

    ns = {"ns": root.tag.split('}')[0].strip('{')} if "}" in root.tag else {}
    build = root.find(".//ns:build", ns) if ns else root.find(".//build")

    if build is None:
        print("⚠️  No build info found.")
        return

    scan_type_label = "Dynamic Scan" if getattr(args, "scan_type", "").lower() == "ds" else "Static Scan"
    print(f"\n✅ Build Info ({scan_type_label}):")
    for k, v in build.attrib.items():
        print(f"  {k}: {v}")
