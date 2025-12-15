import os
import sys
import json
import requests
from datetime import datetime
from veracode_api_signing.plugin_requests import RequestsAuthPluginVeracodeHMAC
from xml_api_cli.config import api_base_rest
from xml_api_cli.utils.api_helpers import (
    find_app_by_name,
    get_latest_build_id,
    fetch_summary_report,
)
from colorama import Fore, Style, init

init(autoreset=True)

HELP_TEXT = "💬 Fetch summary report (XML/PDF or REST JSON) for a specific app/build."

# ----------------------------------------------------------------------
# Parser Setup
# ----------------------------------------------------------------------
def setup_parser(parser):
    parser.add_argument("-i", "--app_id", help="Veracode App ID (XML only, required if --app_name not used)")
    parser.add_argument("-n", "--app_name", help="Veracode App Name (required if --app_id not used)")
    parser.add_argument("-g", "--guid", help="Application GUID (for specific REST details lookup).")
    parser.add_argument("-f", "--format", choices=["XML", "PDF"], help="Report format (required for XML)")
    parser.add_argument("-s", "--scan_type", choices=["ss", "ds"], default="ss", help="Scan type (required for XML)")
    parser.add_argument("-r", "--region", choices=["us", "eu", "us_fed"], default="us", help="Region for API requests")
    parser.add_argument("-t", "--api_type", choices=["XML", "REST"], default="XML", help="API type to use (default: XML)")
    parser.add_argument("-o", "--output_dir", default=None, help="Directory to save report (optional)")
    parser.add_argument("-p", "--prefix", help="Filename prefix (optional)")

# ----------------------------------------------------------------------
# REST Helpers
# ----------------------------------------------------------------------
def find_app_rest_by_name(app_name: str, region: str = "us"):
    base_url = api_base_rest(region).rstrip("/")
    url = f"{base_url}/appsec/v1/applications/?name={app_name}"
    params = {"size": 100, "page": 0}
    total_apps = []
    while True:
        resp = requests.get(url, params=params, auth=RequestsAuthPluginVeracodeHMAC(), timeout=10)
        if resp.status_code != 200:
            print(f"⚠️  Failed to fetch application (HTTP {resp.status_code}): {resp.text}")
            break

        data = resp.json()
        applications = data.get("_embedded", {}).get("applications", [])
        if not apps:
            break
        total_apps.extend(applications)

        # 🧾 Pagination info
        page_info = data.get("page", {})
        current_page = page_info.get("number", 0)
        total_pages = page_info.get("total_pages", 1)

        print(f"📄 Processed page {current_page + 1}/{total_pages} ({len(applications)} applications)")

        # Exit if this was the last page
        if current_page >= total_pages - 1:
            break

        params["page"] = current_page + 1  # move to next page
    
    if total_apps:
        data = {"_embedded": {"applications": total_apps}}
        apps = data.json().get("_embedded", {}).get("applications", [])
        
    return [{"name": a.get("profile", {}).get("name"), "guid": a.get("guid"), "last_scan": a.get("last_completed_scan_date", "-")} for a in apps]

# ----------------------------------------------------------------------
# Summary Helpers
# ----------------------------------------------------------------------
def color_text(text, sev):
    colors = {'5': Fore.RED + Style.BRIGHT, '4': Fore.LIGHTRED_EX + Style.BRIGHT, '3': Fore.YELLOW, '2': Fore.CYAN, '1': Fore.CYAN, '0': Fore.CYAN}
    return f"{colors.get(sev, Fore.WHITE)}{text}{Style.RESET_ALL}"

def summarize_module(module):
    return {str(i): module.get(f"numflawssev{i}", 0) for i in range(6)}

def print_analysis_section(title, modules, rating=None, icon='🧩'):
    print(f"\n{icon} {title}")
    for idx, mod in enumerate(modules, 1):
        print(f"  🧩 Module {idx}: {mod.get('name', '-')}")
        print(f"    • Score: {mod.get('score', '-')}")
        if rating: print(f"    • Rating: {rating}")
        sev_counts = summarize_module(mod)
        print(f"    • Findings:")
        for sev in reversed(range(6)):
            count = sev_counts[str(sev)]
            if count > 0:
                sev_label = f"Sev 5 (Very High)" if sev==5 else "Sev 4 (High)" if sev==4 else "Sev 3 (Medium)" if sev==3 else "Sev 2 (Low)" if sev==2 else "Sev 1 (Very Low)" if sev==1  else "Sev 0 (Info)"
                print(f"      {color_text('🔴' if sev==5 else '🟠' if sev==4 else '🟡' if sev==3 else '🟢' if sev==2 else '🔵', str(sev))} {sev_label}: {count}")

def print_manual_analysis(manual_data):
    modules = manual_data.get('modules', {}).get('module', [])
    if modules:
        print_analysis_section('Manual Pen Testing (MPT)', modules, rating=manual_data.get('rating'), icon='📝')

def print_rest_summary(data: dict):
    print("\n📊 REST Summary Report:")
    print("="*70)

    app_name = data.get("app_name", "-")
    app_id = data.get("app_id", "-")
    version = data.get("version", "-")
    last_scan = data.get("last_update_time", "-")
    policy = data.get("policy_name", "-")
    policy_status = data.get("policy_compliance_status", "-")
    total_flaws = data.get("total_flaws", "-")
    mitigated = data.get("flaws_not_mitigated", "-")

    print(f"🧱 Application:     {app_name}")
    print(f"🆔 APP ID:          {app_id}")
    print(f"🧩 Scan Name:       {version}")
    print(f"📅 Last Scan:       {last_scan}")
    print(f"📋 Policy:          {policy}")
    print(f"✅ Policy Status:   {policy_status}")
    print(f"⚠️ Total Flaws:     {total_flaws}")
    print(f"🧠 Flaws Not Mitigated: {mitigated}")
    print("-"*70)

    for analysis_type, title, icon in [
        ("static-analysis", "Static Analysis (SAST)", "🧠"),
        ("dynamic-analysis", "Dynamic Analysis (DAST)", "🌐"),
        ("manual-analysis", "Manual Pen Testing (MPT)", "📝")
    ]:
        section = data.get(analysis_type)
        if section:
            modules = section.get("modules", {}).get("module", [])
            if not isinstance(modules, list): modules = [modules]
            if analysis_type == 'manual-analysis':
                print_manual_analysis(section)
            else:
                print_analysis_section(title, modules, rating=section.get('rating'), icon=icon)

    sca = data.get("software_composition_analysis")
    if sca:
        comp_wrapper = sca.get("vulnerable_components", {})
        components = comp_wrapper.get("component_dto", [])

        total_components = len(components)

        total_vulns = sum(
            len(c.get("vulnerabilities", {}).get("vulnerability_dto", []))
            for c in components
        )

        print(f"\n📦 Software Composition Analysis (SCA)")
        print(f"  Vulnerable Components: {total_components}")
        print(f"  Total Vulnerabilities: {total_vulns}")

    print("="*70)

# ----------------------------------------------------------------------
# XML Helper (unchanged)
# ----------------------------------------------------------------------
def find_app_id_by_name(app_name: str, region: str = "us") -> str | None:
    apps = find_app_by_name(app_name, region)
    if not apps:
        return None
    if len(apps) == 1:
        app = apps[0]
        print(f"✅ Found application: {app['app_name']}\t(ID: {app['app_id']})\t(Last Policy Check: {app['last_policy_update']})")
        return app["app_id"]
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

# ----------------------------------------------------------------------
# Main Run
# ----------------------------------------------------------------------
def run(args):
    print("📘 Task: Fetch Summary Report")
    try:
        if args.guid:
            guid = args.guid
            report_url = f"{api_base_rest(args.region).rstrip('/')}/appsec/v2/applications/{guid}/summary_report"
            resp = requests.get(report_url, auth=RequestsAuthPluginVeracodeHMAC(), timeout=30)
            if resp.status_code != 200:
                print(f"❌ Failed to fetch REST summary report ({resp.status_code}): {resp.text}")
                sys.exit(1)
            data = resp.json()
            print_rest_summary(data)
            return
        if args.api_type == "REST":
            if not args.app_name:
                print("❌ REST API requires --app_name to search applications.")
                sys.exit(1)
            matches = find_app_rest_by_name(args.app_name, args.region)
            if not matches:
                print("❌ No applications found.")
                sys.exit(1)
            if len(matches) == 1:
                guid = matches[0]["guid"]
                app_name = matches[0]["name"]
            else:
                print("\n⚠️  Multiple matches found:")
                for i, app in enumerate(matches, 1):
                    print(f"  [{i}] {app['name']:<35}  (GUID: {app['guid']})  Last Scan: {app['last_scan']}")
                while True:
                    choice = input("Enter the number of the app to download report for: ").strip()
                    if choice.isdigit() and 1 <= int(choice) <= len(matches):
                        guid = matches[int(choice)-1]["guid"]
                        app_name = matches[int(choice)-1]["name"]
                        break
                    print("Invalid selection. Try again.")
            report_url = f"{api_base_rest(args.region).rstrip('/')}/appsec/v2/applications/{guid}/summary_report"
            resp = requests.get(report_url, auth=RequestsAuthPluginVeracodeHMAC(), timeout=30)
            if resp.status_code != 200:
                print(f"❌ Failed to fetch REST summary report ({resp.status_code}): {resp.text}")
                sys.exit(1)
            data = resp.json()
            print_rest_summary(data)
            if args.output_dir:
                os.makedirs(args.output_dir, exist_ok=True)
                prefix = args.prefix or "summary_report"
                filename = f"{prefix}_{app_name.replace('/', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                file_path = os.path.join(args.output_dir, filename)
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                print(f"💾 JSON report saved at: {os.path.abspath(file_path)}")
            return

        # XML mode (unchanged)
        if not args.format or not args.scan_type:
            print("❌ For XML mode, both --format (-f) and --scan_type (-s) are required.")
            sys.exit(1)
        app_id = args.app_id
        if not app_id and args.app_name:
            print(f"Resolving app_id for app_name='{args.app_name}' ...")
            app_id = find_app_id_by_name(args.app_name)
        if not app_id:
            print("❌ Please provide a valid app_id or app_name.")
            return
        print(f"Fetching latest build for app_id={app_id} (scan_type={args.scan_type}) ...")
        build_id = get_latest_build_id(app_id, args.scan_type)
        if not build_id:
            print("❌ No valid build found for the specified scan type. Exiting.")
            return
        print(f"📄 Downloading {args.format} report for build_id={build_id} ...")
        os.makedirs(args.output_dir or ".", exist_ok=True)
        file_path = fetch_summary_report(app_id, build_id, args.format, args.output_dir or ".", args.prefix)
        print(f"✅ Report downloaded successfully: {os.path.abspath(file_path)}")
    except KeyboardInterrupt:
        print("\n🛑 Operation cancelled.")
    except Exception as e:
        print(f"❌ Error: {e}")