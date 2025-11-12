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
# 🧩 Function: Fetch all users (paginated, tabular)
# ----------------------------------------------------------------------
def list_all_users(region: str):
    """
    Fetch all users and print them in tabular format.
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

            # Pagination check
            page_info = data.get("page", {})
            current_page = page_info.get("number", 0)
            total_pages = page_info.get("total_pages", 1)
            if current_page + 1 >= total_pages:
                break
            params["page"] += 1

        # 🧮 Prepare table
        if not total_users:
            print("⚠️  No users found.")
            return

        headers = ["Active", "Name", "Email", "User ID", "Username", "Login Enabled"]
        rows = []
        for u in total_users:
            status_icon = "🟢" if u.get("active") else "🔴"
            name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
            email = u.get("email_address", "")
            uid = u.get("user_id", "")
            uname = u.get("user_name", "")
            login_status = "✅" if u.get("login_enabled") else "❌"
            rows.append([status_icon, name, email, uid, uname, login_status])

        # 🧱 Compute column widths
        col_widths = [max(len(str(row[i])) for row in ([headers] + rows)) for i in range(len(headers))]

        # 🪶 Print table
        print("\n" + " | ".join(headers[i].ljust(col_widths[i]) for i in range(len(headers))))
        print("-" * (sum(col_widths) + (3 * (len(headers) - 1))))

        for row in rows:
            print(" | ".join(str(row[i]).ljust(col_widths[i]) for i in range(len(headers))))

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

            teams = data.get("teams", [])
            if teams:
                print(f"\n👥 Teams ({len(teams)}):")
                for t in teams:
                    print(f"   • {t.get('team_name')} ({t.get('relationship', {}).get('display_name', '')})")

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
# 🎯 Main Function
# ----------------------------------------------------------------------
def run(args=None):
    if args.user:
        if args.user.lower() == "all":
            list_all_users(args.region)