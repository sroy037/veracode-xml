import subprocess
import json


def handle_veracli_command(command_text: str, user_id: str) -> str:
    """
    Run a veracli command and return Slack-formatted output.
    """
    try:
        # Run command
        process = subprocess.Popen(
            ["veracli"] + command_text.split(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        stdout, stderr = process.communicate()
        exit_code = process.returncode

        # Format stdout nicely
        try:
            parsed_json = json.loads(stdout)
            stdout_fmt = "```json\n" + json.dumps(parsed_json, indent=2) + "\n```"
        except Exception:
            stdout_fmt = "```\n" + stdout + "\n```"

        # Final Slack message (NO ``` inside f-string)
        reply = (
            f"*🧩 Command Executed:*\n"
            f"`veracli {command_text}`\n\n"

            f"📤 *Output:*\n"
            f"{stdout_fmt}\n\n"

            f"⚠️ *stderr:*\n"
            f"```\n{stderr}\n```\n\n"

            f"*Exit Code:* `{exit_code}`"
        )

        return reply

    except Exception as e:
        return f"❌ *Error executing veracli command:* `{e}`"