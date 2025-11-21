import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from event_handler import handle_veracli_command

# Slack credentials
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

app = App(token=SLACK_BOT_TOKEN)


@app.command("/veracli")
def veracli_handler(ack, body, respond):
    """
    Slash command handler for Slack.
    """
    ack()

    user_input = body.get("text", "").strip()
    user_id = body.get("user_id")

    if not user_input:
        respond("⚠️ Please provide a command to run.\nExample: `/veracli app_list`")
        return

    # Delegate processing
    response = handle_veracli_command(user_input, user_id)

    respond(response)


if __name__ == "__main__":
    print("🚀 Slack bot running...")
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()