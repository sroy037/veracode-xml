import os
import requests
import xml.etree.ElementTree as ET
from xml_api_cli.config import (
    endpoint_getapplist,
    endpoint_getappinfo,
    endpoint_getbuildlist,
    endpoint_getbuildinfo,
    endpoint_detailedreport_xml,
    endpoint_detailedreport_pdf,
    endpoint_summaryreport_xml,
    endpoint_summaryreport_pdf,
    endpoint_mitigationreviewer,
    DEFAULT_REGION,
)
from veracode_api_signing.plugin_requests import RequestsAuthPluginVeracodeHMAC

def _parse_xml_with_ns(text):
    """
    Parse XML text and return tuple (root, ns_map)
    where ns_map is a dict like {'ns': <namespace_uri>} if namespace exists.
    """
    root = ET.fromstring(text)
    ns_map = {}
    if "}" in root.tag:
        uri = root.tag.split("}")[0].strip("{")
        ns_map = {"ns": uri}
    return root, ns_map

def get_app_id_from_name(app_name: str, region: str = DEFAULT_REGION) -> str | None:
    """Look up app_id for a given application name, handling namespace correctly."""
    url = endpoint_getapplist(region)
    resp = requests.get(url, auth=RequestsAuthPluginVeracodeHMAC())
    resp.raise_for_status()

    root, ns = _parse_xml_with_ns(resp.text)
    # pick the correct tag path
    if ns:
        apps = root.findall(".//ns:app", ns)
    else:
        apps = root.findall(".//app")

    for app in apps:
        if app.get("app_name") == app_name:
            return app.get("app_id")

    return None

def get_latest_build_id(app_id: str, scan_type: str = "ss", region: str = DEFAULT_REGION) -> str | None:
    """
    Fetch latest build_id depending on scan type.
    scan_type: "ss" (Static) or "ds" (Dynamic)
    """
    if scan_type == "ds":
        url = endpoint_getbuildlist(region) + f"?app_id={app_id}"
        resp = requests.get(url, auth=RequestsAuthPluginVeracodeHMAC())
        resp.raise_for_status()
        root, ns = _parse_xml_with_ns(resp.text)
        if ns:
            builds = root.findall(".//ns:build", ns)
        else:
            builds = root.findall(".//build")

        ds_builds = [b for b in builds if b.get("dynamic_scan_type") == "ds" and b.get("policy_updated_date")]
        if not ds_builds:
            return None

        latest = max(ds_builds, key=lambda b: b.get("policy_updated_date", ""))
        return latest.get("build_id")

    else:
        url = endpoint_getbuildinfo(region) + f"?app_id={app_id}"
        resp = requests.get(url, auth=RequestsAuthPluginVeracodeHMAC())
        resp.raise_for_status()
        root, ns = _parse_xml_with_ns(resp.text)

        if ns:
            build_elem = root.find(".//ns:build", ns)
        else:
            build_elem = root.find(".//build")

        if build_elem is not None:
            return build_elem.get("build_id")

        return None

def fetch_detailed_report(app_id: str, build_id: str, format_type: str, output_dir: str, prefix: str, region: str = DEFAULT_REGION) -> str | None:
    """Download detailed report (XML or PDF) and save locally."""
    format_type = format_type.upper()
    if format_type == "PDF":
        url = endpoint_detailedreport_pdf(region) + f"?build_id={build_id}&app_id={app_id}"
        extension = "pdf"
    else:
        url = endpoint_detailedreport_xml(region) + f"?build_id={build_id}&app_id={app_id}"
        extension = "xml"

    resp = requests.get(url, auth=RequestsAuthPluginVeracodeHMAC())
    resp.raise_for_status()

    os.makedirs(os.path.expanduser(output_dir), exist_ok=True)
    filename = f"{f'{prefix}_' if prefix else ''}{app_id}_{build_id}_detailed_report.{extension}"
    filepath = os.path.join(os.path.expanduser(output_dir), filename)

    with open(filepath, "wb") as f:
        f.write(resp.content)

    return filepath

def fetch_summary_report(app_id: str, build_id: str, format_type: str, output_dir: str, prefix: str, region: str = DEFAULT_REGION) -> str | None:
    """Download Summary report (XML or PDF) and save locally."""
    format_type = format_type.upper()
    if format_type == "PDF":
        url = endpoint_summaryreport_pdf(region) + f"?build_id={build_id}&app_id={app_id}"
        extension = "pdf"
    else:
        url = endpoint_summaryreport_xml(region) + f"?build_id={build_id}&app_id={app_id}"
        extension = "xml"

    resp = requests.get(url, auth=RequestsAuthPluginVeracodeHMAC())
    resp.raise_for_status()

    os.makedirs(os.path.expanduser(output_dir), exist_ok=True)
    filename = f"{f'{prefix}_' if prefix else ''}{app_id}_{build_id}_summary_report.{extension}"
    filepath = os.path.join(os.path.expanduser(output_dir), filename)

    with open(filepath, "wb") as f:
        f.write(resp.content)

    return filepath

def find_app_by_name(app_name: str, region: str = DEFAULT_REGION) -> str | None:
    """
    Returns a list of matching apps (partial match supported).
    Each item is a dict with app_id and app_name.
    """
    import xml.etree.ElementTree as ET
    
    url = endpoint_getapplist(region)
    response = requests.get(url, auth=RequestsAuthPluginVeracodeHMAC())

    if response.status_code != 200:
        print(f"❌ Failed to fetch app list ({response.status_code})")
        return []
    
    root = ET.fromstring(response.text)
    ns = {"ns": "https://analysiscenter.veracode.com/schema/2.0/applist"}  # namespace
    
    matches = []
    for app in root.findall("ns:app", ns):
        name = app.attrib.get("app_name", "")
        policy_upd = app.attrib.get("policy_updated_date", "")
        if app_name.lower() in name.lower():
            matches.append({"app_id": app.attrib["app_id"], "app_name": name, "last_policy_update": policy_upd})
    return matches

def fetch_mitigation_info(app_id: str, build_id: str, issue_ids: str, region: str = DEFAULT_REGION) -> list[dict]:
    """Fetch Mitigation for the provided Issue List."""
    import xml.etree.ElementTree as ET
    
    url = endpoint_mitigationreviewer(region) + f"?build_id={build_id}&flaw_id_list={issue_ids}"
    response = requests.get(url, auth=RequestsAuthPluginVeracodeHMAC())

    root = ET.fromstring(response.text)

    # Define namespace
    ns = {"v": "https://analysiscenter.veracode.com/schema/mitigationinfo/1.0"}

    mitigations_list = []

    # Traverse <issue> elements
    for issue in root.findall("v:issue", ns):
        flaw_id = issue.attrib.get("flaw_id")
        category = issue.attrib.get("category", "")
        actions = []

        for ma in issue.findall("v:mitigation_action", ns):
            actions.append({
                "action": ma.attrib.get("action"),
                "desc": ma.attrib.get("desc"),
                "reviewer": ma.attrib.get("reviewer"),
                "date": ma.attrib.get("date"),
                "comment": ma.attrib.get("comment")
            })

        mitigations_list.append({
            "flaw_id": flaw_id,
            "category": category,
            "mitigations": actions
        })

    return mitigations_list

def fetch_build_issues(app_id: str, build_id: str, region: str = DEFAULT_REGION) -> list[dict]:
    """
    Fetch issues for given app_id and latest build_id from Veracode Detailed Report (XML).
    """
    url = endpoint_detailedreport_xml(region) + f"?build_id={build_id}&app_id={app_id}"
    response = requests.get(url, auth=RequestsAuthPluginVeracodeHMAC())
    response.raise_for_status()
    root = ET.fromstring(response.text)

    # Extract default namespace
    ns = {"v": "https://www.veracode.com/schema/reports/export/1.0"}

    total_flaws = int(root.attrib.get("total_flaws", "0"))
    if total_flaws == 0:
        return []

    issues = []
    # staticflaws → flaw
    for cwe in root.findall(".//v:cwe", ns):
        for staticflaws in cwe.findall("v:staticflaws", ns):
            for flaw in staticflaws.findall("v:flaw", ns):
                # Optional: skip third-party SCA (they have type="software_composition_analysis")
                flaw_type = flaw.attrib.get("type", "")
                if flaw_type.lower() == "software_composition_analysis":
                    continue

                issues.append({
                    "issueid": str(flaw.attrib.get("issueid")),  # force string
                    "title": str(flaw.attrib.get("categoryname") or flaw.attrib.get("category")),
                    "severity": flaw.attrib.get("severity"),
                    "cweid": flaw.attrib.get("cweid"),
                    "module": flaw.attrib.get("module"),
                    "description": flaw.attrib.get("description"),
                    "mitigation_status": flaw.attrib.get("mitigation_status"),
                    "mitigation_status_desc": flaw.attrib.get("mitigation_status_desc"),
                    "sourcefile": flaw.attrib.get("sourcefile"),
                    "line": flaw.attrib.get("line"),
                })

    # dynamicflaws → flaw
    for sev in root.findall(".//v:severity", ns):
        severity_level = sev.get("level")
        
        for cat in sev.findall(".//v:category", ns):
            category_name = cat.get("categoryname")
    
            for cwe in cat.findall(".//v:cwe", ns):
                cwe_id = cwe.get("cweid")
                cwe_name = cwe.get("cwename")
    
                # handle dynamic flaws
                for flaw in cwe.findall(".//v:dynamicflaws/v:flaw", ns):
                    # Optional: skip third-party SCA (they have type="software_composition_analysis")
                    flaw_type = flaw.attrib.get("type", "")
                    if flaw_type.lower() == "software_composition_analysis":
                        continue
    
                    issues.append({
                        "issueid": flaw.get("issueid"),
                        "severity": flaw.get("severity", severity_level),
                        "module": category_name,
                        "type": flaw.get("type"),
                        "cwe_id": cwe_id,
                        "cwe_name": cwe_name,
                        "title": flaw.get("description"),
                        "remediation_status": flaw.get("remediation_status"),
                        "mitigation_status": flaw.get("mitigation_status_desc"),
                        "date_first_occurrence": flaw.get("date_first_occurrence"),
                        "vuln_parameter": flaw.get("vuln_parameter"),
                    })
    return issues

def select_issues_interactively(issues: list[dict], severity: str | None = None) -> list[str]:
    """
    Display issues categorized by severity and let the user select which to fetch mitigation info for.
    If `severity` is provided, only issues of that severity are shown.
    Issues are sorted by numeric issue_id for readability.
    """
    severity_map = {
        "5": "Very High",
        "4": "High",
        "3": "Medium",
        "2": "Low",
        "1": "Very Low",
        "0": "Info"
    }

    # Categorize issues
    categorized = {label: [] for label in severity_map.values()}
    categorized["Info"] = []  # ensure "Info" exists

    for issue in issues:
        sev_num = str(issue.get("severity", "0"))
        sev_label = severity_map.get(sev_num, "Info")
        categorized[sev_label].append(issue)

    # Sort issues by numeric issue_id
    for key in categorized:
        categorized[key].sort(key=lambda i: int(i.get("issueid", "0")))

    # Determine which severities to show
    severity_order = ["Very High", "High", "Medium", "Low", "Very Low", "Info"]
    if severity:
        if severity in categorized:
            severity_order = [severity]
        else:
            print(f"⚠️ Invalid severity '{severity}'. Showing all severities instead.")
    
    # Display issues
    print("\n📌 Issues by Severity:")
    selectable = []
    idx = 1
    for sev_label in severity_order:
        if categorized[sev_label]:
            print(f"\n=== {sev_label} ===")
            for issue in categorized[sev_label]:
                issue_id = issue.get("issueid")
                title = issue.get("title") or "(No Title)"
                module = issue.get("module") or ""
                print(f"  [{idx}] {issue_id} - {title} ({module})")
                selectable.append(issue_id)
                idx += 1

    if not selectable:
        print("⚠️  No issues found for the selected severity.")
        return []

    # Interactive selection
    selection = input("\nEnter numbers of issues to fetch mitigation info (comma-separated): ").strip()
    if not selection:
        print("⚠️  No issues selected. Exiting.")
        return []

    try:
        selected_nums = [int(x.strip()) for x in selection.split(",") if x.strip().isdigit()]
        selected_ids = [selectable[i - 1] for i in selected_nums if 0 < i <= len(selectable)]
    except Exception:
        print("❌ Invalid selection. Please enter valid issue numbers.")
        return []

    return selected_ids

def save_output(content: str, args, task_name: str):
    """
    Save API response content to a file.
    File name: <prefix><task_name>_<app_id or app_name>.xml
    """
    output_dir = getattr(args, "output_dir", None) or os.path.expanduser("~/veracode_reports")
    os.makedirs(output_dir, exist_ok=True)

    prefix = getattr(args, "prefix", "")
    identifier = getattr(args, "app_id", getattr(args, "app_name", "output"))
    ext = "xml"  # default save as XML; PDF tasks can override

    filename = f"{prefix}{task_name}_{identifier}.{ext}"
    file_path = os.path.join(output_dir, filename)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✅ Saved output to {file_path}")
    return file_path

def pretty_print_xml(xml_string: str):
    """
    Pretty-print XML to console.
    """
    try:
        dom = xml.dom.minidom.parseString(xml_string)
        pretty = dom.toprettyxml()
        print(pretty)
    except Exception:
        # fallback if parsing fails
        print(xml_string)
