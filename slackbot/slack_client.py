import os
from slack_sdk import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.socket_mode.request import SocketModeRequest


class SlackBotClient:
    def __init__(self):
        self.app_token = os.getenv("SLACK_APP_TOKEN")  # xapp- token
        self.bot_token = os.getenv("SLACK_BOT_TOKEN")  # xoxb- token

        if not self.app_token or not self.bot_token:
            raise ValueError("Slack tokens not set in environment variables")

        # Web API client
        self.web_client = WebClient(token=self.bot_token)

        # Socket Mode client
        self.socket_client = SocketModeClient(
            app_token=self.app_token,
            web_client=self.web_client
        )

    def start(self, event_handler):
        """
        Start listening for Slack events and route them to event_handler.
        """
        @self.socket_client.socket_mode_request_listeners.append
        def handle_events(client: SocketModeClient, req: SocketModeRequest):
            # Acknowledge Slack request
            response = SocketModeResponse(envelope_id=req.envelope_id)
            client.send_socket_mode_response(response)

            # Forward messages to the event_handler
            if req.type == "events_api":
                event = req.payload.get("event", {})
                event_handler(event, client=self.web_client)

        print("🚀 Slack bot started (Socket Mode). Waiting for messages…")
        self.socket_client.connect()
        self.socket_client.wait_for_events()