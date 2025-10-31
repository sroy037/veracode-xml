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
    filename = f"{prefix}{app_id}_{build_id}_report.{extension}"
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
    filename = f"{prefix}{app_id}_{build_id}_report.{extension}"
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
