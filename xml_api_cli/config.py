"""
xml_api_cli.config

Centralized configuration for Veracode XML/REST API endpoints and defaults.

Notes:
- XML APIs (legacy) are served from analysiscenter.veracode.* domains.
- REST APIs are served from api.veracode.* domains.
- See Veracode docs for Region Domains and XML API reference.
  https://docs.veracode.com/r/c_api_main
  https://docs.veracode.com/r/Region_Domains_for_Veracode_APIs
"""

from __future__ import annotations
import os
from typing import Literal

Region = Literal["us", "eu", "us_fed"]

# ---------------------------------------------------------------------
# Version / metadata
# ---------------------------------------------------------------------
TOOL_NAME = "xml-api-cli"
VERSION = os.getenv("XML_API_CLI_VERSION", "1.0.0")
DESCRIPTION = "CLI utilities for Veracode XML/REST APIs (modular tasks)."

# ---------------------------------------------------------------------
# Environment overrides (optional)
# Use these to override endpoints (useful for testing or private proxies)
# ---------------------------------------------------------------------
ENV_XML_API_CLI_BASE = os.getenv("XML_API_CLI_BASE")         # e.g. https://analysiscenter.veracode.com/api/
ENV_VERACODE_REST_BASE = os.getenv("VERACODE_REST_BASE")       # e.g. https://api.veracode.com/

# ---------------------------------------------------------------------
# Canonical domain prefixes (per Veracode docs)
# - XML APIs (legacy): analysiscenter.veracode.com (Commercial)
# - REST APIs: api.veracode.com (Commercial)
#
# European (EU) region: analysiscenter.veracode.eu, api.veracode.eu
# US Federal region (if needed): analysiscenter.veracode.us, api.veracode.us
# ---------------------------------------------------------------------
_REGION_DOMAINS = {
    "us": {
        "xml": "https://analysiscenter.veracode.com/api/",
        "rest": "https://api.veracode.com/",
    },
    "eu": {
        "xml": "https://analysiscenter.veracode.eu/api/",
        "rest": "https://api.veracode.eu/",
    },
    "us_fed": {
        "xml": "https://analysiscenter.veracode.us/api/",
        "rest": "https://api.veracode.us/",
    },
}

# ---------------------------------------------------------------------
# Default region and file paths
# ---------------------------------------------------------------------
DEFAULT_REGION: Region = os.getenv("VERACODE_REGION", "us")  # "us" or "eu" or "us_fed"
DEFAULT_OUTPUT_DIR = os.path.expanduser(os.getenv("VERACODE_OUTPUT_DIR", "~/veracode_reports"))
CREDENTIALS_FILE = os.path.expanduser(os.getenv("VERACODE_CREDENTIALS_FILE", "~/.veracode/credentials"))

# ---------------------------------------------------------------------
# Helpers to get API base URLs (handles environment overrides)
# ---------------------------------------------------------------------
def api_base_xml(region: Region = DEFAULT_REGION) -> str:
    """
    Returns the XML API base URL for the requested region.
    Example: https://analysiscenter.veracode.com/api/5.0/
    Note: callers should append the API version/endpoint as needed.
    """
    # Allow full override via env var
    if ENV_XML_API_CLI_BASE:
        base = ENV_XML_API_CLI_BASE
        if not base.endswith("/"):
            base += "/"
        return base

    region_entry = _REGION_DOMAINS.get(region)
    if not region_entry:
        raise ValueError(f"Unknown region: {region}")
    # keep trailing api/ – callers will append "5.0/" or "4.0/" as appropriate
    return region_entry["xml"]

def api_base_rest(region: Region = DEFAULT_REGION) -> str:
    """
    Returns the REST API base URL for the requested region.
    Example: https://api.veracode.com/
    """
    if ENV_VERACODE_REST_BASE:
        base = ENV_VERACODE_REST_BASE
        if not base.endswith("/"):
            base += "/"
        return base

    region_entry = _REGION_DOMAINS.get(region)
    if not region_entry:
        raise ValueError(f"Unknown region: {region}")
    return region_entry["rest"]

# ---------------------------------------------------------------------
# Short helper functions for common XML API versions/endpoints
# - Many XML endpoints are under /api/5.0/
# - Some older endpoints (PDF detailed report) use /api/4.0/
# ---------------------------------------------------------------------
def xml_api_v5_base(region: Region = DEFAULT_REGION) -> str:
    """Base prefix for XML v5 endpoints (e.g. getbuildlist.do, detailedreport.do)."""
    base = api_base_xml(region)
    if not base.endswith("/"):
        base += "/"
    return f"{base}5.0/"

def xml_api_v4_base(region: Region = DEFAULT_REGION) -> str:
    """Base prefix for XML v4 endpoints (used for some PDF endpoints)."""
    base = api_base_xml(region)
    if not base.endswith("/"):
        base += "/"
    return f"{base}4.0/"

# ---------------------------------------------------------------------
# Convenience: endpoints for common actions
# (callers may still build full URLs, these are helpers)
# ---------------------------------------------------------------------
def endpoint_getapplist(region: Region = DEFAULT_REGION) -> str:
    return xml_api_v5_base(region) + "getapplist.do"

def endpoint_getappinfo(region: Region = DEFAULT_REGION) -> str:
    return xml_api_v5_base(region) + "getappinfo.do"

def endpoint_getbuildlist(region: Region = DEFAULT_REGION) -> str:
    return xml_api_v5_base(region) + "getbuildlist.do"

def endpoint_getbuildinfo(region: Region = DEFAULT_REGION) -> str:
    return xml_api_v5_base(region) + "getbuildinfo.do"

def endpoint_detailedreport_xml(region: Region = DEFAULT_REGION) -> str:
    return xml_api_v5_base(region) + "detailedreport.do"

def endpoint_detailedreport_pdf(region: Region = DEFAULT_REGION) -> str:
    # PDF endpoint is historically on v4
    return xml_api_v4_base(region) + "detailedreportpdf.do"

def endpoint_summaryreport_xml(region: Region = DEFAULT_REGION) -> str:
    # XML endpoint is historically on v4
    return xml_api_v4_base(region) + "summaryreport.do"

def endpoint_summaryreport_pdf(region: Region = DEFAULT_REGION) -> str:
    # PDF endpoint is historically on v4
    return xml_api_v4_base(region) + "summaryreportpdf.do"

# ---------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------
def ensure_output_dir(path: str = DEFAULT_OUTPUT_DIR) -> str:
    os.makedirs(os.path.expanduser(path), exist_ok=True)
    return os.path.expanduser(path)
