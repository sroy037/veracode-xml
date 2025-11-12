import os
import sys
import argparse
import requests
from datetime import datetime, timezone
from configparser import ConfigParser
from veracode_api_signing.plugin_requests import RequestsAuthPluginVeracodeHMAC
from xml_api_cli.utils.api_helpers import get_veracode_api_url

HELP_TEXT = "🔐 Validate Veracode API credentials from ~/.veracode/credentials or fetch detailed user information."

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
        default="all",
        help="Fetch user details by user ID or 'all' for list (default: all). Admin only."
    )

# ----------------------------------------------------------------------
# 🧩 Function: Fetch all users (paginated)
# ----------------------------------------------------------------------
def list_all_users(region: str):
    """
    Fetch all users with pagination support.
    """
    base_url = "https://api.veracode.com/api/authn/v2/users"
    params = {"size": 100, "page": 0}
    total_users = []
    print("📡 Fetching all users...")

    try:
        while True:
            resp = requests.get(base_url, params=params, auth=RequestsAuthPluginVeracodeHMAC(), timeout=10)
            if resp.status_code != 200:
                print(f"⚠️  Failed to fetch users (HTTP {resp.status_code}): {resp.text}")
                break

            data = resp.json()
            users = data.get("_embedded", {}).get("users", [])
            if not users:
                break

            total_users.extend(users)

            # Pagination info
            page_info = data.get("page", {})
            current_page = page_info.get("number", 0)
            total_pages = page_info.get("total_pages", 1)

            for u in users:
                status_icon = "🟢" if u.get("active") else "🔴"
                login_icon = "🔑" if u.get("login_enabled") else "🚫"
                print(f"\n{status_icon} {u.get('first_name', '')} {u.get('last_name', '')} "
                      f"({u.get('email_address')})")
                print(f"   🆔 User ID: {u.get('user_id')}")
                print(f"   👤 Username: {u.get('user_name')}")
                print(f"   {login_icon} Login Enabled: {u.get('login_enabled')}")
                print(f"   🔗 Self Link: {u.get('_links', {}).get('self', {}).get('href')}")

            if current_page + 1 >= total_pages:
                break
            params["page"] += 1

        print(f"\n✅ Retrieved total {len(total_users)} users.")
    except requests.exceptions.RequestException as e:
        print(f"❌ Connection error: {e}")

# ----------------------------------------------------------------------
# 🧩 Function: Fetch specific user details
# ----------------------------------------------------------------------
def get_user_details(user_id: str, region: str):
    """
    Fetch detailed user info and API credentials from Veracode API.
    """
    base_url = "https://api.veracode.com/api/authn/v2"
    url = f"{base_url}/users/{user_id}"
    print(f"📡 Fetching user details for user_id: {user_id}")

    try:
        resp = requests.get(url, auth=RequestsAuthPluginVeracodeHMAC(), timeout=10)
        if resp.status_code == 200:
            data = resp.json()

            print("\n✅ User details retrieved successfully:\n")
            print(f"👤 Name: {data.get('first_name', '')} {data.get('last_name', '')}")
            print(f"📧 Email: {data.get('email_address')}")
            print(f"🏢 Organization: {data.get('organization', {}).get('org_name', 'N/A')}")
            print(f"🔑 Login Enabled: {data.get('login_enabled', False)}")
            print(f"🟢 Active: {data.get('active', False)}")

            # --- API Credentials Section ---
            api_creds = data.get("api_credentials")
            if not api_creds:
                print("\n⚠️  API Credentials were never generated for this user.")
            else:
                print("\n🔐 API Credential Details:")
                print(f"   🆔 API ID: {api_creds.get('api_id')}")
                exp_ts = api_creds.get("expiration_ts")
                print(f"   📅 Expiration: {exp_ts}")
                try:
                    exp_dt = datetime.strptime(exp_ts.split(".")[0], "%Y-%m-%dT%H:%M:%S")
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                    days_left = (exp_dt - datetime.now(timezone.utc)).days
                    if days_left >= 0:
                        print(f"   ⏳ Expires in: {days_left} day(s)")
                    else:
                        print(f"   ⚠️  Expired {-days_left} day(s) ago.")
                except Exception:
                    pass

            # --- Teams Summary ---
            teams = data.get("teams", [])
            if teams:
                print(f"\n👥 Teams ({len(teams)}):")
                for t in teams:
                    print(f"   • {t.get('team_name')} ({t.get('relationship', {}).get('display_name', '')})")

            # --- Roles Summary ---
            roles = data.get("roles", [])
            if roles:
                print(f"\n🧩 Roles ({len(roles)}):")
                for r in roles:
                    print(f"   • {r.get('role_description', r.get('role_name'))}")

            print("\n✅ User information retrieved successfully.")
        elif resp.status_code == 403:
            print("❌ Access denied. Admin privileges required to fetch user details.")
        elif resp.status_code == 404:
            print("⚠️  User not found.")
        else:
            print(f"⚠️  Unexpected response ({resp.status_code}): {resp.text}")

    except requests.exceptions.RequestException as e:
        print(f"❌ Connection error: {e}")

# ----------------------------------------------------------------------
# 🎯 Main Function: Validate default creds or fetch user info
# ----------------------------------------------------------------------
def run(args=None):
    """
    Fetch [default] credentials and check API validity,
    or fetch user details if --user is provided.
    """
    if args.user:
        if args.user.lower() == "all":
            list_all_users(args.region)
            return
        else:
            get_user_details(args.user, args.region)
            return

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
