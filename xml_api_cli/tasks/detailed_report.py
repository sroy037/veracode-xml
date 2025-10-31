import os
from xml_api_cli.utils.api_helpers import (
    find_app_by_name,
    get_latest_build_id,
    fetch_detailed_report,
)

HELP_TEXT = "Fetch detailed report (XML/PDF) for a specific app/build."

def setup_parser(parser):
    parser.add_argument("-i", "--app_id", help="Veracode App ID (required if --app_name not used)")
    parser.add_argument("-n", "--app_name", help="Veracode App Name (required if --app_id not used)")
    parser.add_argument("-f", "--format", choices=["XML", "PDF"], required=True, help="Report format")
    parser.add_argument("-s", "--scan_type", choices=["ss", "ds"], default="ss", help="Scan type (ss=Static, ds=Dynamic)")
    parser.add_argument("-r", "--region", choices=["us","eu","gov"], default="us", help="Region for API requests")
    parser.add_argument("-o", "--output_dir", default=".", help="Directory to save report")
    parser.add_argument("-p", "--prefix", help="Filename prefix")

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
    print("📘 Task: Fetch Detailed Report")

    # Determine app_id
    app_id = args.app_id
    if not app_id and args.app_name:
        print(f"Resolving app_id for app_name='{args.app_name}' ...")
        app_id = find_app_id_by_name(args.app_name)

    if not app_id:
        print("❌ Please provide a valid app_id or app_name.")
        return

    # Fetch build_id
    print(f"Fetching latest build for app_id={app_id} (scan_type={args.scan_type or 'ss'}) ...")
    build_id = get_latest_build_id(app_id, args.scan_type)

    if not build_id:
        print("❌ No valid build found for the specified scan type. Exiting.")
        return

    # Fetch report
    print(f"📄 Downloading {args.format} report for build_id={build_id} ...")
    os.makedirs(args.output_dir, exist_ok=True)
    fetch_detailed_report(app_id, build_id, args.format, args.output_dir, args.prefix)
    print("✅ Report downloaded successfully.")
