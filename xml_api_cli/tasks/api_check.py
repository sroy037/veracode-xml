import os
import sys
import requests
from datetime import datetime, timezone
from configparser import ConfigParser
from veracode_api_signing.plugin_requests import RequestsAuthPluginVeracodeHMAC
from xml_api_cli.utils.api_helpers import get_veracode_api_url

HELP_TEXT = "🔐 Validate Veracode API credentials from ~/.veracode/credentials."

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

def run(args=None):
    """
    Fetch [default] credentials and check API validity
    """
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

            print(f"\n✅ Credentials are valid!")
            print(f"🆔 API ID: {api_id}")
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
