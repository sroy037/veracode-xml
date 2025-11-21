import os
import sys
import argparse
from time import sleep
import requests
from datetime import datetime, timezone
from configparser import ConfigParser
from veracode_api_signing.plugin_requests import RequestsAuthPluginVeracodeHMAC
from xml_api_cli.utils.api_helpers import get_veracode_api_url
from xml_api_cli.config import api_base_rest

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
        help="Fetch user details by user ID or 'all' for list (optional). Admin only."
    )
    parser.add_argument(
        "-s", "--search",
         choices=["name", "email", "api_id"],
        help="Search users by Username, Email ID, API ID, etc. Admin only."
    )
    parser.add_argument(
        "-v", "--value",
        help="Search value"
    )

# ----------------------------------------------------------------------
# 🧩 Function: Fetch all users (paginated, tabular)
# ----------------------------------------------------------------------
def list_all_users(region: str):
    """
    Fetch all users and print them in tabular format with pagination.
    """
    base_url = api_base_rest(region).rstrip("/")
    url = f"{base_url}/api/authn/v2/users"
    params = {"size": 300, "page": 0}
    total_users = []
    print("📡 Fetching all users...")

    try:
        while True:
            resp = requests.get(url, params=params, auth=RequestsAuthPluginVeracodeHMAC(), timeout=10)
            if resp.status_code != 200:
                print(f"⚠️  Failed to fetch users (HTTP {resp.status_code}): {resp.text}")
                break

            data = resp.json()
            users = data.get("_embedded", {}).get("users", [])
            if not users:
                break
            total_users.extend(users)

            # 🧾 Pagination info
            page_info = data.get("page", {})
            current_page = page_info.get("number", 0)
            total_pages = page_info.get("total_pages", 1)

            print(f"📄 Processed page {current_page + 1}/{total_pages} ({len(users)} users)")

            # Exit if this was the last page
            if current_page >= total_pages - 1:
                break

            params["page"] = current_page + 1  # move to next page

        # 🧮 Prepare table
        if not total_users:
            print("⚠️  No users found.")
            return

        headers = ["Name", "Email", "User ID", "Username", "Login Enabled"]
        rows = []
        for u in total_users:
            #status_icon = "🟢" if u.get("active") else "🔴"
            name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
            email = u.get("email_address", "")
            uid = u.get("user_id", "")
            uname = u.get("user_name", "")
            login_status = "✅" if u.get("login_enabled") else "❌"
            # if uid:
            #     base_url = api_base_rest(region).rstrip("/")
            #     url = f"{base_url}/api/authn/v2/users/{uid}"
            #     sleep(1)
            #     try:
            #         resp = requests.get(url, auth=RequestsAuthPluginVeracodeHMAC(), timeout=10)
            #         if resp.status_code == 200:
            #             data = resp.json()
            #             api_creds = data.get("api_credentials")
            #             if not api_creds:
            #                 status_icon = "🟡 - Never Generated"
            #             else:
            #                 exp_ts = api_creds.get("expiration_ts")
            #                 try:
            #                     exp_dt = datetime.strptime(exp_ts.split(".")[0], "%Y-%m-%dT%H:%M:%S")
            #                     exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            #                     days_left = (exp_dt - datetime.now(timezone.utc)).days
            #                     if days_left >= 0:
            #                         status_icon = "🟢 - Active"
            #                     else:
            #                         status_icon = "🔴 - Expired"
            #                 except Exception:
            #                     pass

            #         elif resp.status_code == 403:
            #             print("❌ Access denied. Admin privileges required to fetch user details.")
            #         elif resp.status_code == 404:
            #             print("⚠️  User not found.")
            #         else:
            #             print(f"⚠️  Unexpected response ({resp.status_code}): {resp.text}")

            #     except requests.exceptions.RequestException as e:
            #         print(f"❌ Connection error: {e}")
            rows.append([name, email, uid, uname, login_status])

        # 🧱 Compute column widths dynamically
        col_widths = [max(len(str(row[i])) for row in ([headers] + rows)) for i in range(len(headers))]

        # 🪶 Print table
        print("\n" + " | ".join(headers[i].ljust(col_widths[i]) for i in range(len(headers))))
        print("-" * (sum(col_widths) + (3 * (len(headers) - 1))))

        for row in rows:
            print(" | ".join(str(row[i]).ljust(col_widths[i]) for i in range(len(headers))))

        print(f"\n✅ Retrieved total {len(total_users)} users across {page_info.get('total_pages', 1)} page(s).")

    except requests.exceptions.RequestException as e:
        print(f"❌ Connection error: {e}")

# ----------------------------------------------------------------------
# 🧩 Function: Fetch specific user details
# ----------------------------------------------------------------------
def get_user_details(user_id: str, region: str):
    """
    Fetch detailed user info and API credentials from Veracode API.
    """
    base_url = api_base_rest(region).rstrip("/")
    url = f"{base_url}/api/authn/v2/users/{user_id}"
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
                print(f"   🆔 API ID: {api_creds.get('api_id')[:4]}{'*' * (len(api_creds.get('api_id'))//2 - 4)}{api_creds.get('api_id')[len(api_creds.get('api_id'))//2:]}")
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
            else:
                print(f"\n👥 No Team Restriction.")

            roles = data.get("roles", [])
            if roles:
                print(f"\n🧩 Roles ({len(roles)}):")
                for r in roles:
                    print(f"   • {r.get('role_description', r.get('role_name'))}")
            else:
                print(f"\n👥 No Role(s) assigned.")

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
# 🧩 Function: Search User
# ----------------------------------------------------------------------
def get_user_by_search(search_id: str, search_val: str, region: str):
    """
    Search User by Username, Email Address or API ID.
    """
    if search_id == "name":
        base_url = api_base_rest(region).rstrip("/")
        url = f"{base_url}/api/authn/v2/users?user_name={search_val}"
    elif search_id == "email":
        encoded_email = search_val.replace("@", "%40")
        base_url = api_base_rest(region).rstrip("/")
        url = f"{base_url}/api/authn/v2/users?email_address={encoded_email}"
    elif search_id == "api_id":
        base_url = api_base_rest(region).rstrip("/")
        url = f"{base_url}/api/authn/v2/users/search?api_id={search_val}"

    params = {"size": 300, "page": 0}
    total_users = []
    print("📡 Searching all users...")

    try:
        while True:
            resp = requests.get(url, params=params, auth=RequestsAuthPluginVeracodeHMAC(), timeout=10)
            if resp.status_code != 200:
                print(f"⚠️  Failed to fetch users (HTTP {resp.status_code}): {resp.text}")
                break

            data = resp.json()
            users = data.get("_embedded", {}).get("users", [])
            if not users:
                break
            total_users.extend(users)

            # 🧾 Pagination info
            page_info = data.get("page", {})
            current_page = page_info.get("number", 0)
            total_pages = page_info.get("total_pages", 1)

            print(f"📄 Processed page {current_page + 1}/{total_pages} ({len(users)} users)")

            # Exit if this was the last page
            if current_page >= total_pages - 1:
                break

            params["page"] = current_page + 1  # move to next page

        # 🧮 Prepare table
        if not total_users:
            print("⚠️  No users found.")
            return

        headers = ["User Status", "Name", "Email", "User ID", "Username", "Login Enabled"]
        rows = []
        for u in total_users:
            status_icon = "🟢" if u.get("active") else "🔴"
            name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
            email = u.get("email_address", "")
            uid = u.get("user_id", "")
            uname = u.get("user_name", "")
            login_status = "✅" if u.get("login_enabled") else "❌"
            rows.append([status_icon, name, email, uid, uname, login_status])

        if search_id == "api_id":
            get_user_details(uid, region)
        else:
        # 🧱 Compute column widths dynamically
            col_widths = [max(len(str(row[i])) for row in ([headers] + rows)) for i in range(len(headers))]

            # 🪶 Print table
            print("\n" + " | ".join(headers[i].ljust(col_widths[i]) for i in range(len(headers))))
            print("-" * (sum(col_widths) + (3 * (len(headers) - 1))))

            for row in rows:
                print(" | ".join(str(row[i]).ljust(col_widths[i]) for i in range(len(headers))))

            print(f"\n✅ Retrieved total {len(total_users)} users across {page_info.get('total_pages', 1)} page(s).")

    except requests.exceptions.RequestException as e:
        print(f"❌ Connection error: {e}")


# ----------------------------------------------------------------------
# 🎯 Main Function
# ----------------------------------------------------------------------
def run(args=None):
    if args.user:
        if args.user.lower() == "all":
            list_all_users(args.region)
        else:
            get_user_details(args.user, args.region)
    elif args.search:
        # Added logic for Unified search
        get_user_by_search(args.search, args.value, args.region)
    else:
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