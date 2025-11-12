import os
import sys
import argparse
import requests
from datetime import datetime, timezone
from configparser import ConfigParser
from veracode_api_signing.plugin_requests import RequestsAuthPluginVeracodeHMAC
from xml_api_cli.utils.api_helpers import get_veracode_api_url

HELP_TEXT = "🔐 Validate Veracode API credentials from ~/.veracode/credentials or fetch user-specific API keys."

def setup_parser(parser: argparse.ArgumentParser):
    """
    Setup argparse for this task.
    """
    parser.add_argument(
        "-r", "--region",
        default="us",
        choices=["us", "eu", "us_fed"],
        help="Region for Veracode platform (default: us)."
    )
    parser.add_argument(
        "-u", "--user",
        help="Fetch API credentials for a specific user ID (Admin only)."
    )

# ----------------------------------------------------------------------
# 🧩 New Function: Fetch API creds by User ID
# ----------------------------------------------------------------------
def get_user_api_creds(user_id: str, region: str):
    """
    Fetch API credentials for the given Veracode user ID.
    """
    base_url = get_veracode_api_url(region)
    # Force base API root (authn API is not region-specific in helper)
    if "api/authn/v2" not in base_url:
        base_url = "https://api.veracode.com/api/authn/v2"
    url = f"{base_url}/api_credentials/user_id/{user_id}"

    print(f"📡 Fetching API credentials for user_id: {user_id}")
    try:
        resp = requests.get(url, auth=RequestsAuthPluginVeracodeHMAC(), timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            print("✅ User API credentials retrieved successfully:\n")
            print(f"🆔 API ID: {data.get('api_id')}")
            print(f"🔑 API Key Prefix: {data.get('api_key_prefix', 'N/A')}")
            print(f"📅 Created: {data.get('creation_ts', 'Unknown')}")
            print(f"📅 Expires: {data.get('expiration_ts', 'Unknown')}")
        elif resp.status_code == 403:
            print("❌ Access denied. Admin privilege required to fetch user credentials.")
        elif resp.status_code == 404:
            print("⚠️  User not found or does not have API credentials.")
        else:
            print(f"⚠️  Unexpected response ({resp.status_code}): {resp.text}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Connection error: {e}")

# ----------------------------------------------------------------------
# 🎯 Main Function: Validate or delegate to user creds fetch
# ----------------------------------------------------------------------
def run(args=None):
    """
    Fetch [default] credentials and check API validity,
    or fetch user-specific credentials if --user is provided.
    """
    if args.user:
        get_user_api_creds(args.user, args.region)
        return  # Skip default validation when user flag is used

    cred_file = os.path.expanduser("~/.veracode/credentials")

    if not os.path.exists(cred_file):
        print(f"❌ Credentials file not found at {cred_file}")
        sys.exit(1)

    config = ConfigParser()
    config.read(cred_file)

    if "default" not in config:
        print("⚠️  [default] section not found in credentials file.")
        sys.exit(1)

    api_id = config.get("default", "veracode_api_key_id", fallback=None)
    api_key = config.get("default", "veracode_api_key_secret", fallback=None)

    if not api_id or not api_key:
        print("❌ Missing API credentials in [default] section.")
        sys.exit(1)

    print("🔍 Validating Veracode credentials...")
    print(f"📡 Using region: {args.region}")

    url = get_veracode_api_url(args.region)

    try:
        resp = requests.get(url, auth=RequestsAuthPluginVeracodeHMAC(), timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            exp_str = data.get("expiration_ts")
            api_id = data.get("api_id")
            user_id = data.get("user_id")

            print(f"\n✅ Credentials are valid!")
            print(f"🆔 API ID: {api_id}")
            print(f"🧑‍ User ID: {user_id}")
            print(f"📅 Expiration: {exp_str}")

            # --- Calculate days until expiry ---
            if exp_str:
                try:
                    exp_dt = datetime.strptime(exp_str.split(".")[0], "%Y-%m-%dT%H:%M:%S")
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                    now_utc = datetime.now(timezone.utc)
                    days_left = (exp_dt - now_utc).days

                    if days_left >= 0:
                        print(f"⏳ Expires in: {days_left} day(s)")
                    else:
                        print(f"⚠️  Credentials expired {-days_left} day(s) ago.")
                except Exception:
                    print("⚠️  Could not parse expiration timestamp.")
        elif resp.status_code == 401:
            print("❌ Invalid credentials or expired keys or incorrect region.")
        else:
            print(f"⚠️  Unexpected response ({resp.status_code}): {resp.text}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Connection error: {e}")
