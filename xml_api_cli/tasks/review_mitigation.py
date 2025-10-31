"""
Fetch mitigation details for issues using Veracode XML API.
Reference: https://docs.veracode.com/r/r_getmitigationinfo
"""

import os
import xml.etree.ElementTree as ET
from xml_api_cli import config
from xml_api_cli.utils.api_helpers import (
    find_app_by_name,
    get_latest_build_id,
    fetch_mitigation_info,
    select_issues_interactively,
    fetch_build_issues,
)

HELP_TEXT = "Fetch mitigation information for issues."

def setup_parser(parser):
    parser.add_argument(
        "-i", "--app_id",
        help="Application ID (required if --app_name not provided)"
    )
    parser.add_argument(
        "-n", "--app_name",
        help="Veracode App Name (required if --app_id not used)"
    )
    parser.add_argument(
        "-f", "--file",
        help="XML file containing issues (optional)"
    )
    parser.add_argument(
        "-r", "--region",
        choices=["us", "eu", "us_fed"],
        default="us",
        help="Region for API requests"
    )
    parser.add_argument(
        "-s", "--scan_type",
        choices=["ss", "ds"],
        default="ss",
        help="Scan type (ss=Static, ds=Dynamic)"
    )
    parser.add_argument(
        "-S", "--severity",
        choices=["Very High", "High", "Medium", "Low", "Very Low", "Info"],
        help="Severity Filter"
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
    print("📘 Task: Review Mitigation Information")

    # If file is provided, parse issue IDs
    if args.file:
        if not os.path.exists(args.file):
            print(f"❌ File '{args.file}' does not exist. Exiting.")
            return
        tree = ET.parse(args.file)
        root = tree.getroot()
        issue_ids = [elem.get("issue_id") for elem in root.findall(".//issue")]
        print(f"📄 Loaded {len(issue_ids)} issue(s) from file '{args.file}'")
    else:
        # Resolve app_id if only app_name is provided
        app_id = args.app_id
        if not app_id and args.app_name:
            print(f"🔍 Resolving app_id for app_name='{args.app_name}' ...")
            app_id = find_app_id_by_name(args.app_name, args.region)

        if not app_id:
            print("❌ Please provide a valid app_id or app_name.")
            return
    
        # Fetch build_id
        print(f"Fetching latest build for app_id={app_id} (scan_type={args.scan_type or 'ss'}) ...")
        build_id = get_latest_build_id(app_id, args.scan_type)
    
        if not build_id:
            print("❌ No valid build found for the specified scan type. Exiting.")
            return
        print(f"📦 Using latest build_id={build_id}")

        # Fetch issues from build
        issues = fetch_build_issues(app_id, build_id, args.region)
        if not issues:
            print("❌ No issues found in latest build. Exiting.")
            return

    # Let user select issues
    issue_ids = select_issues_interactively(issues, args.severity)
    if not issue_ids:
        print("⚠️  No issues selected. Exiting.")
        return

    print(f"📡 Fetching mitigation info for {len(issue_ids)} issue(s)...")
    selected_ids = ",".join([str(i) for i in issue_ids])
    mitigations = fetch_mitigation_info(app_id, build_id, selected_ids, region=args.region)

    if not mitigations:
        print("❌ No mitigation details found for provided issue(s).")
    else:
        print("\n✅ Mitigation Details:")
        for m in mitigations:
            print(f"\n• Issue: {m['flaw_id']} - {m['category']}")
            if not m['mitigations']:
                print("  (No mitigations)")
                continue
            for ma in m['mitigations']:
                print(f"  • Action: {ma['action']}")
                print(f"    Desc: {ma['desc']}")
                print(f"    Reviewer: {ma.get('reviewer','N/A')}")
                print(f"    Date: {ma.get('date','N/A')}")
                print(f"    Comment: {ma.get('comment','(No comment)')}")
