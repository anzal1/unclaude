"""Messaging integrations for UnClaude.

Lets users interact with UnClaude via Telegram and WhatsApp.
Messages come in -> get processed as tasks -> responses go back.
Task completions from the daemon also get forwarded.

Supports:
- Telegram Bot API (free, self-hosted, long-polling)
- WhatsApp via Twilio (paid API) or Green API (free, QR scan)
- Generic webhook (for Slack, Discord, etc.)

Dead-easy setup:
    unclaude messaging setup telegram    # paste bot token, done
    unclaude messaging setup whatsapp    # paste Green API creds, done

Usage:
    from unclaude.messaging import get_messenger, TelegramAdapter
    messenger = get_messenger()
    await messenger.send("Task completed!", channel="telegram")
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Awaitable

import httpx

logger = logging.getLogger(__name__)


# ── Data Types ──────────────────────────────────────────

class Platform(str, Enum):
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    WEBHOOK = "webhook"


@dataclass
class IncomingMessage:
    """A message received from any platform."""
    platform: Platform
    chat_id: str           # platform-specific chat/conversation ID
    sender_id: str         # who sent it
    sender_name: str       # display name
    text: str              # the actual message
    timestamp: float = field(default_factory=time.time)
    raw: dict = field(default_factory=dict)  # original payload
    reply_to: str | None = None  # message ID being replied to
    message_id: str | None = None


@dataclass
class OutgoingMessage:
    """A message to send to a platform."""
    platform: Platform
    chat_id: str
    text: str
    parse_mode: str | None = "Markdown"  # Markdown, HTML, or None
    reply_to_message_id: str | None = None


# ── Adapter Base ────────────────────────────────────────

MessageHandler = Callable[[IncomingMessage], Awaitable[str | None]]


class MessagingAdapter(ABC):
    """Base class for messaging platform adapters."""

    platform: Platform

    @abstractmethod
    async def send(self, msg: OutgoingMessage) -> bool:
        """Send a message. Returns True on success."""
        ...

    @abstractmethod
    async def handle_webhook(self, payload: dict) -> IncomingMessage | None:
        """Parse an incoming webhook payload into an IncomingMessage."""
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if this adapter has the required credentials."""
        ...

    @abstractmethod
    def get_setup_instructions(self) -> str:
        """Return human-readable setup instructions."""
        ...


# ── Telegram Adapter ───────────────────────────────────

class TelegramAdapter(MessagingAdapter):
    """Telegram Bot API adapter.

    Setup:
    1. Message @ BotFather on Telegram -> /newbot
    2. Copy the bot token
    3. Run: unclaude messaging setup telegram - -token YOUR_BOT_TOKEN
    4. Start the bot: it will set up a webhook automatically

    Or set env var: UNCLAUDE_TELEGRAM_BOT_TOKEN
    """

    platform = Platform.TELEGRAM
    API_BASE = "https://api.telegram.org/bot{token}"

    def __init__(self, bot_token: str | None = None):
        self.bot_token = bot_token or os.environ.get(
            "UNCLAUDE_TELEGRAM_BOT_TOKEN", "")
        self._allowed_chat_ids: set[str] = set()
        self._http: httpx.AsyncClient | None = None

    @property
    def api_url(self) -> str:
        return self.API_BASE.format(token=self.bot_token)

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=30.0)
        return self._http

    def is_configured(self) -> bool:
        return bool(self.bot_token)

    def get_setup_instructions(self) -> str:
        return """Telegram Bot Setup:
1. Open Telegram and search for @ BotFather
2. Send / newbot and follow the prompts
3. Copy the bot token(looks like 123456: ABC-DEF...)
4. Run: unclaude messaging setup telegram
5. Paste the token when prompted

The bot will automatically:
- Accept / start to register your chat
- Accept / task < description > to submit tasks
- Accept / status to check daemon status
- Send you notifications when tasks complete"""

    async def _api_call(self, method: str, data: dict | None = None) -> dict:
        """Make a Telegram Bot API call."""
        client = await self._client()
        url = f"{self.api_url}/{method}"
        try:
            if data:
                resp = await client.post(url, json=data)
            else:
                resp = await client.get(url)
            resp.raise_for_status()
            result = resp.json()
            if not result.get("ok"):
                logger.error(f"Telegram API error: {result}")
            return result
        except Exception as e:
            logger.error(f"Telegram API call failed ({method}): {e}")
            return {"ok": False, "error": str(e)}

    async def set_webhook(self, webhook_url: str) -> bool:
        """Register webhook URL with Telegram."""
        result = await self._api_call("setWebhook", {
            "url": webhook_url,
            "allowed_updates": ["message"],
            "drop_pending_updates": True,
        })
        return result.get("ok", False)

    async def delete_webhook(self) -> bool:
        """Remove webhook(for switching to polling)."""
        result = await self._api_call("deleteWebhook")
        return result.get("ok", False)

    async def get_me(self) -> dict:
        """Get bot info to verify token."""
        result = await self._api_call("getMe")
        return result.get("result", {})

    async def send(self, msg: OutgoingMessage) -> bool:
        """Send a message to a Telegram chat."""
        data: dict[str, Any] = {
            "chat_id": msg.chat_id,
            "text": msg.text,
        }
        if msg.parse_mode:
            data["parse_mode"] = msg.parse_mode
        if msg.reply_to_message_id:
            data["reply_to_message_id"] = msg.reply_to_message_id

        # Telegram has a 4096 char limit — split long messages
        if len(msg.text) > 4000:
            chunks = _split_message(msg.text, 4000)
            for chunk in chunks:
                data["text"] = chunk
                result = await self._api_call("sendMessage", data)
                if not result.get("ok"):
                    # Retry without parse_mode (bad Markdown is common)
                    if "parse_mode" in data:
                        plain = dict(data)
                        del plain["parse_mode"]
                        plain["text"] = chunk
                        result = await self._api_call("sendMessage", plain)
                    if not result.get("ok"):
                        return False
            return True

        result = await self._api_call("sendMessage", data)
        if not result.get("ok") and "parse_mode" in data:
            # Retry without parse_mode — bad Markdown causes 400
            plain = {k: v for k, v in data.items() if k != "parse_mode"}
            result = await self._api_call("sendMessage", plain)
        return result.get("ok", False)

    async def send_with_buttons(
        self, chat_id: str, text: str, buttons: list[list[dict[str, str]]],
        parse_mode: str = "Markdown",
    ) -> bool:
        """Send a message with inline keyboard buttons.

        Args:
            buttons: List of rows, each row is a list of {"text": ..., "callback_data": ...}
        """
        data: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": {"inline_keyboard": buttons},
        }
        if parse_mode:
            data["parse_mode"] = parse_mode
        result = await self._api_call("sendMessage", data)
        return result.get("ok", False)

    async def handle_webhook(self, payload: dict) -> IncomingMessage | None:
        """Parse a Telegram webhook update."""
        message = payload.get("message")
        if not message:
            return None

        text = message.get("text", "")
        if not text:
            return None

        chat = message.get("chat", {})
        sender = message.get("from", {})

        return IncomingMessage(
            platform=Platform.TELEGRAM,
            chat_id=str(chat.get("id", "")),
            sender_id=str(sender.get("id", "")),
            sender_name=sender.get("first_name", "") +
            " " + sender.get("last_name", ""),
            text=text,
            timestamp=message.get("date", time.time()),
            raw=payload,
            message_id=str(message.get("message_id", "")),
        )

    # ── Long-Polling Mode ──────────────────────────

    async def get_updates(self, offset: int = 0, timeout: int = 30) -> list[dict]:
        """Fetch new updates via long-polling(no webhook needed).

        Args:
            offset: ID of the first update to return (use last update_id + 1)
            timeout: Long-poll timeout in seconds(Telegram holds connection open)

        Returns:
            List of update dicts from the Telegram API.
        """
        params: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset:
            params["offset"] = offset

        # Use a longer HTTP timeout than the long-poll timeout
        client = await self._client()
        try:
            resp = await client.get(
                f"{self.api_url}/getUpdates",
                params=params,
                timeout=timeout + 10,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("ok"):
                return data.get("result", [])
            logger.error(f"getUpdates error: {data}")
            return []
        except httpx.ReadTimeout:
            # Normal — long-poll expired with no updates
            return []
        except Exception as e:
            logger.error(f"getUpdates failed: {e}")
            return []

    async def start_polling(
        self,
        messenger: Any,
        interval: float = 1.0,
        shutdown_event: asyncio.Event | None = None,
    ) -> None:
        """Run continuous long-polling loop.

        This is the easiest way to receive messages — no public URL needed.
        Just start polling, open Telegram, message your bot.

        Args:
            messenger: Messenger instance(calls messenger.process_and_reply)
            interval: Seconds between polls when no updates(backoff)
            shutdown_event: Optional event to stop polling gracefully
        """
        _stop = shutdown_event or asyncio.Event()

        # Must delete any active webhook — Telegram won't return updates
        # via getUpdates while a webhook is set
        await self.delete_webhook()

        bot_info = await self.get_me()
        bot_name = bot_info.get("username", "unknown")
        logger.info(f"Telegram polling started for @{bot_name}")

        # Also accept callback_query updates (button presses)
        # added to allowed_updates in get_updates below

        offset = 0
        consecutive_errors = 0
        max_backoff = 30
        _pending_tasks: set[asyncio.Task] = set()

        while not _stop.is_set():
            try:
                updates = await self.get_updates(offset=offset, timeout=25)
                consecutive_errors = 0  # Reset on success

                for update in updates:
                    update_id = update.get("update_id", 0)
                    offset = update_id + 1  # Acknowledge this update

                    # Handle callback queries (inline button presses)
                    callback = update.get("callback_query")
                    if callback:
                        task = asyncio.create_task(
                            self._handle_callback(callback, messenger)
                        )
                        _pending_tasks.add(task)
                        task.add_done_callback(_pending_tasks.discard)
                        continue

                    msg = await self.handle_webhook(update)
                    if msg:
                        logger.info(
                            f"[Telegram] {msg.sender_name}: {msg.text[:80]}"
                        )
                        # Process concurrently — don't block polling
                        # while the LLM is thinking
                        task = asyncio.create_task(
                            self._safe_process(messenger, msg)
                        )
                        _pending_tasks.add(task)
                        task.add_done_callback(_pending_tasks.discard)

                # Small sleep between polls to avoid hammering
                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                logger.info("Telegram polling cancelled")
                break
            except Exception as e:
                consecutive_errors += 1
                backoff = min(2 ** consecutive_errors, max_backoff)
                logger.error(
                    f"Polling error (retry in {backoff}s): {e}"
                )
                await asyncio.sleep(backoff)

        # Wait for any in-flight message processing to finish
        if _pending_tasks:
            logger.info(
                f"Waiting for {len(_pending_tasks)} pending messages...")
            await asyncio.gather(*_pending_tasks, return_exceptions=True)

        logger.info("Telegram polling stopped")

    @staticmethod
    async def _safe_process(messenger: Any, msg: Any) -> None:
        """Process a message safely, catching all errors."""
        try:
            await messenger.process_and_reply(msg)
        except Exception as e:
            logger.error(
                f"Error processing message from {msg.sender_name}: {e}")

    async def _handle_callback(self, callback: dict, messenger: Any) -> None:
        """Handle an inline keyboard button press."""
        try:
            callback_id = callback.get("id", "")
            data = callback.get("data", "")
            chat = callback.get("message", {}).get("chat", {})
            chat_id = str(chat.get("id", ""))
            sender = callback.get("from", {})

            # Answer the callback to remove "loading" animation
            await self._api_call("answerCallbackQuery", {
                "callback_query_id": callback_id,
            })

            if not data or not chat_id:
                return

            # Convert the callback data into a synthetic message
            msg = IncomingMessage(
                platform=Platform.TELEGRAM,
                chat_id=chat_id,
                sender_id=str(sender.get("id", "")),
                sender_name=sender.get("first_name", ""),
                text=data,  # The callback_data becomes the message text
                raw=callback,
            )
            await messenger.process_and_reply(msg)
        except Exception as e:
            logger.error(f"Callback handling error: {e}")

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()


# ── WhatsApp (Twilio) Adapter ──────────────────────────

class WhatsAppAdapter(MessagingAdapter):
    """WhatsApp adapter via Twilio API.

    Setup:
    1. Create a Twilio account at twilio.com
    2. Enable WhatsApp Sandbox (or get a production number)
    3. Get your Account SID and Auth Token
    4. Run: unclaude messaging setup whatsapp

    Or set env vars:
        UNCLAUDE_TWILIO_ACCOUNT_SID
        UNCLAUDE_TWILIO_AUTH_TOKEN
        UNCLAUDE_TWILIO_WHATSAPP_FROM  (e.g., whatsapp:+14155238886)
    """

    platform = Platform.WHATSAPP
    TWILIO_API = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"

    def __init__(
        self,
        account_sid: str | None = None,
        auth_token: str | None = None,
        from_number: str | None = None,
    ):
        self.account_sid = account_sid or os.environ.get(
            "UNCLAUDE_TWILIO_ACCOUNT_SID", "")
        self.auth_token = auth_token or os.environ.get(
            "UNCLAUDE_TWILIO_AUTH_TOKEN", "")
        self.from_number = from_number or os.environ.get(
            "UNCLAUDE_TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886"
        )
        self._http: httpx.AsyncClient | None = None

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=30.0)
        return self._http

    def is_configured(self) -> bool:
        return bool(self.account_sid and self.auth_token)

    def get_setup_instructions(self) -> str:
        return """WhatsApp (Twilio) Setup:
1. Sign up at https://www.twilio.com
2. Go to Console → Messaging → Try it out → Send a WhatsApp message
3. Follow the sandbox instructions to link your phone
4. Get your Account SID and Auth Token from the dashboard
5. Run: unclaude messaging setup whatsapp
6. Enter your credentials when prompted

For production:
- Apply for a WhatsApp Business number through Twilio
- Set up a webhook URL for incoming messages"""

    async def send(self, msg: OutgoingMessage) -> bool:
        """Send a WhatsApp message via Twilio."""
        client = await self._client()
        url = self.TWILIO_API.format(sid=self.account_sid)

        # Ensure the 'to' number has the whatsapp: prefix
        to_number = msg.chat_id
        if not to_number.startswith("whatsapp:"):
            to_number = f"whatsapp:{to_number}"

        data = {
            "From": self.from_number,
            "To": to_number,
            "Body": msg.text,
        }

        try:
            resp = await client.post(
                url,
                data=data,
                auth=(self.account_sid, self.auth_token),
            )
            if resp.status_code in (200, 201):
                return True
            logger.error(f"Twilio API error: {resp.status_code} {resp.text}")
            return False
        except Exception as e:
            logger.error(f"WhatsApp send failed: {e}")
            return False

    async def handle_webhook(self, payload: dict) -> IncomingMessage | None:
        """Parse a Twilio WhatsApp webhook."""
        body = payload.get("Body", "")
        from_number = payload.get("From", "")
        to_number = payload.get("To", "")

        if not body or not from_number:
            return None

        # Extract name from profile if available
        sender_name = payload.get("ProfileName", from_number)

        return IncomingMessage(
            platform=Platform.WHATSAPP,
            chat_id=from_number,  # We reply to this number
            sender_id=from_number,
            sender_name=sender_name,
            text=body,
            raw=payload,
            message_id=payload.get("MessageSid"),
        )

    def validate_signature(self, url: str, params: dict, signature: str) -> bool:
        """Validate Twilio webhook signature for security."""
        # Build the validation string
        combined = url + "".join(f"{k}{v}" for k, v in sorted(params.items()))
        expected = hmac.new(
            self.auth_token.encode(),
            combined.encode(),
            hashlib.sha1,
        ).digest()
        import base64
        expected_b64 = base64.b64encode(expected).decode()
        return hmac.compare_digest(expected_b64, signature)

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()


# ── WhatsApp (Green API) Adapter ───────────────────────

class WhatsAppGreenAPIAdapter(MessagingAdapter):
    """WhatsApp adapter via Green API — FREE, no Twilio needed.

    Dead-easy setup:
    1. Go to https://green-api.com → Sign up (free tier: 1 instance)
    2. Create an instance → Scan QR code with your WhatsApp
    3. Copy Instance ID + API Token
    4. Run: unclaude messaging setup whatsapp
    5. Done! Your personal WhatsApp number is now the bot.

    How it works:
    - Green API bridges your WhatsApp account via their servers
    - You scan a QR code (like WhatsApp Web)
    - UnClaude can then send/receive messages as you
    - Free tier: 1 instance, sufficient for personal use

    Or set env vars:
        UNCLAUDE_GREEN_API_INSTANCE_ID
        UNCLAUDE_GREEN_API_TOKEN
    """

    platform = Platform.WHATSAPP
    API_BASE = "https://api.green-api.com/waInstance{instance_id}"

    def __init__(
        self,
        instance_id: str | None = None,
        api_token: str | None = None,
        owner_phone: str | None = None,
    ):
        self.instance_id = instance_id or os.environ.get(
            "UNCLAUDE_GREEN_API_INSTANCE_ID", "")
        self.api_token = api_token or os.environ.get(
            "UNCLAUDE_GREEN_API_TOKEN", "")
        # phone number of the owner (for auto-registration)
        self.owner_phone = owner_phone or ""
        self._http: httpx.AsyncClient | None = None
        self._polling = False

    @property
    def api_url(self) -> str:
        return self.API_BASE.format(instance_id=self.instance_id)

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=30.0)
        return self._http

    def is_configured(self) -> bool:
        return bool(self.instance_id and self.api_token)

    def get_setup_instructions(self) -> str:
        return """WhatsApp (Green API) Setup — FREE, 3 steps:

1. Go to https://green-api.com → Sign up (free tier works!)
2. Create an instance → Settings → Scan QR code with your WhatsApp
3. Copy your Instance ID and API Token from the dashboard
4. Run: unclaude messaging setup whatsapp
5. Done! Send "hello" to any chat from your WhatsApp.

Your personal WhatsApp number becomes the bot.
No Twilio, no business account, no monthly fees."""

    async def _api_call(self, method: str, data: dict | None = None) -> dict:
        """Make a Green API call."""
        client = await self._client()
        url = f"{self.api_url}/{method}/{self.api_token}"
        try:
            if data:
                resp = await client.post(url, json=data)
            else:
                resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Green API call failed ({method}): {e}")
            return {"error": str(e)}

    async def get_state(self) -> dict:
        """Check if the WhatsApp instance is connected."""
        return await self._api_call("getStateInstance")

    async def send(self, msg: OutgoingMessage) -> bool:
        """Send a WhatsApp message via Green API."""
        # Green API wants chatId like: 1234567890@c.us (personal) or ...@g.us (group)
        chat_id = msg.chat_id
        if "@" not in chat_id:
            # Strip any non-digit chars and add @c.us
            digits = "".join(c for c in chat_id if c.isdigit())
            chat_id = f"{digits}@c.us"

        result = await self._api_call("sendMessage", {
            "chatId": chat_id,
            "message": msg.text,
        })
        return "idMessage" in result

    async def handle_webhook(self, payload: dict) -> IncomingMessage | None:
        """Parse a Green API webhook/notification."""
        # Green API notification format
        body = payload.get("body", {})
        msg_data = body.get("messageData", {})

        # Only handle text messages
        type_msg = msg_data.get("typeMessage", "")
        if type_msg != "textMessage":
            return None

        text = msg_data.get("textMessageData", {}).get("textMessage", "")
        sender_data = body.get("senderData", {})
        chat_id = sender_data.get("chatId", "")
        sender_name = sender_data.get(
            "senderName", sender_data.get("sender", ""))

        if not text:
            return None

        return IncomingMessage(
            platform=Platform.WHATSAPP,
            chat_id=chat_id,
            sender_id=sender_data.get("sender", chat_id),
            sender_name=sender_name,
            text=text,
            raw=payload,
            message_id=body.get("idMessage"),
        )

    async def receive_notification(self) -> dict | None:
        """Receive a single notification from Green API (polling mode)."""
        result = await self._api_call("receiveNotification")
        if result and "body" in result:
            return result
        return None

    async def delete_notification(self, receipt_id: int) -> None:
        """Acknowledge a notification so it's not returned again."""
        await self._api_call(f"deleteNotification/{receipt_id}")

    async def start_polling(
        self,
        messenger: Any,
        interval: float = 2.0,
        shutdown_event: asyncio.Event | None = None,
    ) -> None:
        """Poll Green API for incoming WhatsApp messages."""
        _stop = shutdown_event or asyncio.Event()
        self._polling = True
        logger.info("WhatsApp (Green API) polling started")

        consecutive_errors = 0
        while not _stop.is_set() and self._polling:
            try:
                notification = await self.receive_notification()
                if notification:
                    receipt_id = notification.get("receiptId")
                    msg = await self.handle_webhook(notification)
                    if msg:
                        logger.info(
                            f"[WhatsApp] {msg.sender_name}: {msg.text[:80]}")
                        await messenger.process_and_reply(msg)
                    # Always acknowledge, even if we didn't process it
                    if receipt_id:
                        await self.delete_notification(receipt_id)
                    consecutive_errors = 0
                else:
                    await asyncio.sleep(interval)
                    consecutive_errors = 0
            except asyncio.CancelledError:
                break
            except Exception as e:
                consecutive_errors += 1
                backoff = min(2 ** consecutive_errors, 30)
                logger.error(
                    f"WhatsApp polling error (retry in {backoff}s): {e}")
                await asyncio.sleep(backoff)

        logger.info("WhatsApp polling stopped")

    async def close(self) -> None:
        self._polling = False
        if self._http:
            await self._http.aclose()


# ── Generic Webhook Adapter ────────────────────────────

class WebhookAdapter(MessagingAdapter):
    """Generic webhook adapter for Slack, Discord, custom bots, etc.

    Sends outgoing messages to a configured webhook URL.
    Expects incoming webhooks to POST JSON with {text, sender, chat_id}.
    """

    platform = Platform.WEBHOOK

    def __init__(self, webhook_url: str | None = None, secret: str | None = None):
        self.webhook_url = webhook_url or os.environ.get(
            "UNCLAUDE_WEBHOOK_URL", "")
        self.secret = secret or os.environ.get("UNCLAUDE_WEBHOOK_SECRET", "")
        self._http: httpx.AsyncClient | None = None

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=30.0)
        return self._http

    def is_configured(self) -> bool:
        return bool(self.webhook_url)

    def get_setup_instructions(self) -> str:
        return """Webhook Setup:
1. Set up a webhook receiver (Slack, Discord, or custom)
2. Run: unclaude messaging setup webhook
3. Enter the webhook URL when prompted

Outgoing format (POST to your URL):
    {"text": "...", "source": "unclaude", "timestamp": "..."}

Incoming format (POST to /api/messaging/webhook):
    {"text": "...", "sender": "user", "chat_id": "channel"}"""

    async def send(self, msg: OutgoingMessage) -> bool:
        """Send a message to the webhook URL."""
        if not self.webhook_url:
            return False

        client = await self._client()
        data = {
            "text": msg.text,
            "source": "unclaude",
            "chat_id": msg.chat_id,
            "timestamp": datetime.now().isoformat(),
        }

        headers = {}
        if self.secret:
            sig = hmac.new(
                self.secret.encode(),
                json.dumps(data).encode(),
                hashlib.sha256,
            ).hexdigest()
            headers["X-Webhook-Signature"] = sig

        try:
            resp = await client.post(self.webhook_url, json=data, headers=headers)
            return resp.status_code < 400
        except Exception as e:
            logger.error(f"Webhook send failed: {e}")
            return False

    async def handle_webhook(self, payload: dict) -> IncomingMessage | None:
        """Parse an incoming generic webhook."""
        text = payload.get("text", "")
        if not text:
            return None

        return IncomingMessage(
            platform=Platform.WEBHOOK,
            chat_id=payload.get("chat_id", "default"),
            sender_id=payload.get("sender", "unknown"),
            sender_name=payload.get(
                "sender_name", payload.get("sender", "unknown")),
            text=text,
            raw=payload,
        )

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()


# ── Messenger (Unified Interface) ──────────────────────

class Messenger:
    """Unified messaging interface across all platforms.

    Handles:
    - Dispatching outgoing messages to the right adapter
    - Processing incoming messages (commands + task submission)
    - Auto-registering chats on first message
    - Notifying registered chats on task events
    - Startup/shutdown alive notifications
    - Periodic heartbeat status reports
    """

    def __init__(self):
        self.adapters: dict[Platform, MessagingAdapter] = {}
        self._registered_chats: dict[Platform, set[str]] = {
            Platform.TELEGRAM: set(),
            Platform.WHATSAPP: set(),
            Platform.WEBHOOK: set(),
        }
        # primary owner per platform
        self._owner_chat_ids: dict[Platform, str] = {}
        self._message_handler: MessageHandler | None = None
        self._config_path = Path.home() / ".unclaude" / "messaging.json"
        self._auto_register = True  # auto-register chats on first message
        # 6 hours between heartbeats (0 = disabled)
        self._heartbeat_interval = 3600 * 6
        self._last_heartbeat: float = 0
        self._load_config()

    def _load_config(self) -> None:
        """Load registered chats and adapter config from disk."""
        if self._config_path.exists():
            try:
                with open(self._config_path) as f:
                    data = json.load(f)
                for platform_str, chat_ids in data.get("registered_chats", {}).items():
                    try:
                        platform = Platform(platform_str)
                        self._registered_chats[platform] = set(chat_ids)
                    except ValueError:
                        pass

                # Load owner chat IDs
                for platform_str, chat_id in data.get("owner_chats", {}).items():
                    try:
                        self._owner_chat_ids[Platform(platform_str)] = chat_id
                    except ValueError:
                        pass

                # Load settings
                settings = data.get("settings", {})
                self._auto_register = settings.get("auto_register", True)
                self._heartbeat_interval = settings.get(
                    "heartbeat_interval", 3600 * 6)

                # Initialize adapters from saved config
                adapters_data = data.get("adapters", {})

                if "telegram" in adapters_data:
                    tg = adapters_data["telegram"]
                    self.adapters[Platform.TELEGRAM] = TelegramAdapter(
                        bot_token=tg.get("bot_token", ""),
                    )

                if "whatsapp" in adapters_data:
                    wa = adapters_data["whatsapp"]
                    # Check which WhatsApp backend is configured
                    if wa.get("backend") == "green_api" or wa.get("instance_id"):
                        self.adapters[Platform.WHATSAPP] = WhatsAppGreenAPIAdapter(
                            instance_id=wa.get("instance_id", ""),
                            api_token=wa.get("api_token", ""),
                            owner_phone=wa.get("owner_phone", ""),
                        )
                    else:
                        self.adapters[Platform.WHATSAPP] = WhatsAppAdapter(
                            account_sid=wa.get("account_sid", ""),
                            auth_token=wa.get("auth_token", ""),
                            from_number=wa.get("from_number", ""),
                        )

                if "webhook" in adapters_data:
                    wh = adapters_data["webhook"]
                    self.adapters[Platform.WEBHOOK] = WebhookAdapter(
                        webhook_url=wh.get("webhook_url", ""),
                        secret=wh.get("secret", ""),
                    )

            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Failed to load messaging config: {e}")

    def _save_config(self) -> None:
        """Persist messaging configuration."""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)

        adapters_data: dict[str, Any] = {}
        for platform, adapter in self.adapters.items():
            if platform == Platform.TELEGRAM and isinstance(adapter, TelegramAdapter):
                adapters_data["telegram"] = {
                    "bot_token": adapter.bot_token,
                }
            elif platform == Platform.WHATSAPP:
                if isinstance(adapter, WhatsAppGreenAPIAdapter):
                    adapters_data["whatsapp"] = {
                        "backend": "green_api",
                        "instance_id": adapter.instance_id,
                        "api_token": adapter.api_token,
                        "owner_phone": adapter.owner_phone,
                    }
                elif isinstance(adapter, WhatsAppAdapter):
                    adapters_data["whatsapp"] = {
                        "backend": "twilio",
                        "account_sid": adapter.account_sid,
                        "auth_token": adapter.auth_token,
                        "from_number": adapter.from_number,
                    }
            elif platform == Platform.WEBHOOK and isinstance(adapter, WebhookAdapter):
                adapters_data["webhook"] = {
                    "webhook_url": adapter.webhook_url,
                    "secret": adapter.secret,
                }

        data = {
            "registered_chats": {
                p.value: list(ids) for p, ids in self._registered_chats.items()
            },
            "owner_chats": {
                p.value: cid for p, cid in self._owner_chat_ids.items()
            },
            "settings": {
                "auto_register": self._auto_register,
                "heartbeat_interval": self._heartbeat_interval,
            },
            "adapters": adapters_data,
        }

        with open(self._config_path, "w") as f:
            json.dump(data, f, indent=2)

    def configure_telegram(self, bot_token: str) -> None:
        """Set up the Telegram adapter."""
        self.adapters[Platform.TELEGRAM] = TelegramAdapter(bot_token=bot_token)
        self._save_config()

    def configure_whatsapp(
        self, account_sid: str, auth_token: str, from_number: str
    ) -> None:
        """Set up the WhatsApp adapter (Twilio backend)."""
        self.adapters[Platform.WHATSAPP] = WhatsAppAdapter(
            account_sid=account_sid,
            auth_token=auth_token,
            from_number=from_number,
        )
        self._save_config()

    def configure_whatsapp_green(
        self, instance_id: str, api_token: str, owner_phone: str = "",
    ) -> None:
        """Set up WhatsApp via Green API (free, QR scan). Dead easy."""
        adapter = WhatsAppGreenAPIAdapter(
            instance_id=instance_id,
            api_token=api_token,
            owner_phone=owner_phone,
        )
        self.adapters[Platform.WHATSAPP] = adapter
        # Auto-register the owner's chat if provided
        if owner_phone:
            digits = "".join(c for c in owner_phone if c.isdigit())
            chat_id = f"{digits}@c.us"
            self._registered_chats[Platform.WHATSAPP].add(chat_id)
            self._owner_chat_ids[Platform.WHATSAPP] = chat_id
        self._save_config()

    def configure_webhook(self, webhook_url: str, secret: str = "") -> None:
        """Set up the generic webhook adapter."""
        self.adapters[Platform.WEBHOOK] = WebhookAdapter(
            webhook_url=webhook_url, secret=secret,
        )
        self._save_config()

    def register_chat(self, platform: Platform, chat_id: str) -> None:
        """Register a chat to receive notifications."""
        self._registered_chats[platform].add(chat_id)
        # First chat registered on a platform becomes the owner
        if platform not in self._owner_chat_ids:
            self._owner_chat_ids[platform] = chat_id
        self._save_config()

    def unregister_chat(self, platform: Platform, chat_id: str) -> None:
        """Stop sending notifications to a chat."""
        self._registered_chats[platform].discard(chat_id)
        self._save_config()

    def auto_register(self, platform: Platform, chat_id: str) -> bool:
        """Auto-register a chat on first message. Returns True if newly registered."""
        if not self._auto_register:
            return False
        if chat_id in self._registered_chats.get(platform, set()):
            return False  # Already registered
        self.register_chat(platform, chat_id)
        logger.info(f"Auto-registered {platform.value} chat: {chat_id}")
        return True

    def set_handler(self, handler: MessageHandler) -> None:
        """Set the handler for incoming messages (called by the daemon)."""
        self._message_handler = handler

    def get_status(self) -> dict[str, Any]:
        """Get the status of all messaging integrations."""
        status: dict[str, Any] = {"platforms": {}}
        for platform in Platform:
            adapter = self.adapters.get(platform)
            status["platforms"][platform.value] = {
                "configured": adapter.is_configured() if adapter else False,
                "registered_chats": len(self._registered_chats.get(platform, set())),
            }
        return status

    # ── Lifecycle Notifications ──────────────────────────

    async def notify_alive(self) -> None:
        """Send 'I'm alive' notification to all registered chats on daemon startup."""
        now = datetime.now().strftime("%H:%M")
        hostname = os.uname().nodename

        # Gather system info for a rich startup message
        model_info = ""
        try:
            from unclaude.config import get_settings
            settings = get_settings()
            provider = settings.default_provider
            pconfig = settings.providers.get(provider)
            if pconfig:
                model_info = f"\n🧠 Model: {pconfig.model}"
        except Exception:
            pass

        budget_info = ""
        try:
            from unclaude.usage import get_usage_tracker
            tracker = get_usage_tracker()
            budget = tracker.get_budget()
            if budget:
                spent = tracker.get_summary(period="today").total_cost_usd
                budget_info = f"\n💰 Budget: ${spent:.2f} / ${budget['limit']:.2f}"
        except Exception:
            pass

        text = (
            f"🟢 *UnClaude is online!*\n\n"
            f"⏰ Started at {now}\n"
            f"🖥 Host: {hostname}"
            f"{model_info}"
            f"{budget_info}\n\n"
            f"Ready for tasks. Send /help for commands."
        )
        await self.send(text)
        logger.info("Sent alive notification to all registered chats")

    async def notify_shutdown(self) -> None:
        """Send 'going offline' notification to all registered chats."""
        now = datetime.now().strftime("%H:%M")

        # Gather session stats
        stats_info = ""
        try:
            from unclaude.autonomous.daemon import AgentDaemon
            status = AgentDaemon.read_status()
            if status:
                uptime_sec = time.time() - status.get("started_at", time.time())
                hours = int(uptime_sec // 3600)
                mins = int((uptime_sec % 3600) // 60)
                stats_info = (
                    f"\n\n📊 Session stats:"
                    f"\n⏱ Uptime: {hours}h {mins}m"
                    f"\n✅ Tasks completed: {status.get('tasks_completed', 0)}"
                    f"\n💰 Cost: ${status.get('total_cost_usd', 0):.4f}"
                )
        except Exception:
            pass

        text = (
            f"🔴 *UnClaude going offline*\n\n"
            f"⏰ Stopped at {now}"
            f"{stats_info}\n\n"
            f"Restart with `unclaude agent start`"
        )
        await self.send(text)
        logger.info("Sent shutdown notification to all registered chats")

    async def send_heartbeat(self) -> None:
        """Send periodic heartbeat with stats to all registered chats."""
        if self._heartbeat_interval <= 0:
            return

        now = time.time()
        if now - self._last_heartbeat < self._heartbeat_interval:
            return  # Not time yet

        self._last_heartbeat = now

        # Gather stats
        try:
            from unclaude.autonomous.daemon import AgentDaemon
            status = AgentDaemon.read_status()
            if not status:
                return

            uptime_sec = now - status.get("started_at", now)
            hours = int(uptime_sec // 3600)
            mins = int((uptime_sec % 3600) // 60)

            from unclaude.usage import get_usage_tracker
            tracker = get_usage_tracker()
            today = tracker.get_summary(period="today")

            text = (
                f"💓 *Heartbeat*\n\n"
                f"🟢 Status: {status.get('status', 'unknown')}\n"
                f"⏱ Uptime: {hours}h {mins}m\n"
                f"✅ Tasks: {status.get('tasks_completed', 0)} done, "
                f"{status.get('queue_pending', 0)} pending\n"
                f"💰 Today: ${today.total_cost_usd:.4f} "
                f"({today.total_requests} requests)\n"
                f"🧠 Tokens: {today.total_tokens:,}"
            )
            await self.send(text)
            logger.info("Sent heartbeat to all registered chats")
        except Exception as e:
            logger.error(f"Heartbeat failed: {e}")

    # ── Sending ─────────────────────────────────────────

    async def send(
        self,
        text: str,
        platform: Platform | None = None,
        chat_id: str | None = None,
    ) -> bool:
        """Send a message. If no platform/chat_id, broadcasts to all registered chats."""
        if platform and chat_id:
            adapter = self.adapters.get(platform)
            if not adapter or not adapter.is_configured():
                logger.warning(f"Adapter {platform} not configured")
                return False
            return await adapter.send(OutgoingMessage(
                platform=platform,
                chat_id=chat_id,
                text=text,
            ))

        # Broadcast to all registered chats
        success = False
        for plat, chat_ids in self._registered_chats.items():
            adapter = self.adapters.get(plat)
            if not adapter or not adapter.is_configured():
                continue
            for cid in chat_ids:
                result = await adapter.send(OutgoingMessage(
                    platform=plat,
                    chat_id=cid,
                    text=text,
                ))
                success = success or result
        return success

    async def notify_task_complete(
        self, task_id: str, description: str, result: str, cost_usd: float
    ) -> None:
        """Notify all registered chats that a task completed.

        Sends the full result — long messages are auto-split into multiple
        Telegram/WhatsApp messages by the adapter's send() method.
        """
        result_text = result.strip() if result else "No output"

        header = (
            f"✅ *Task Completed*\n\n"
            f"*ID:* `{task_id}`\n"
            f"*Task:* {description[:200]}\n"
            f"*Cost:* ${cost_usd:.4f}\n\n"
            f"*Result:*\n"
        )

        # If total fits in one message, send as one
        full = header + result_text
        if len(full) <= 4000:
            await self.send(full)
        else:
            # Send header first, then full result (adapter will split)
            await self.send(header.rstrip())
            await self.send(result_text)

    async def notify_task_failed(
        self, task_id: str, description: str, error: str
    ) -> None:
        """Notify all registered chats that a task failed."""
        text = (
            f"❌ *Task Failed*\n\n"
            f"*ID:* `{task_id}`\n"
            f"*Task:* {description[:200]}\n\n"
            f"*Error:*\n{error}"
        )
        await self.send(text)

    async def notify_budget_warning(self, spend: float, limit: float, pct: float) -> None:
        """Notify about budget threshold."""
        text = (
            f"⚠️ *Budget Warning*\n\n"
            f"*Spent:* ${spend:.4f} / ${limit:.2f}\n"
            f"*Usage:* {pct:.0f}%\n\n"
            f"Set a higher limit or switch to a cheaper model."
        )
        await self.send(text)

    # ── Incoming Message Processing ─────────────────────

    async def handle_incoming(self, msg: IncomingMessage) -> str | None:
        """Process an incoming message from any platform.

        Built-in commands:
            /start              - Register this chat for notifications
            /stop               - Unregister
            /status             - Daemon status
            /task <description> - Submit a task
            /usage              - Show usage stats
            /ping               - Quick alive check
            /models             - Show configured models
            /budget             - Budget status
            /kill               - Remote stop daemon
            /help               - Show commands

        Everything else → forwarded to the message handler (LLM chat).
        """
        text = msg.text.strip()

        # Auto-register on first message (dead easy — just message the bot)
        newly_registered = self.auto_register(msg.platform, msg.chat_id)

        # ── Built-in commands ───────────────────────

        if text == "/start":
            if not newly_registered:
                self.register_chat(msg.platform, msg.chat_id)

            welcome = (
                "🤖 *UnClaude connected!*\n\n"
                "You're set up to receive notifications and control the agent.\n\n"
                "Quick commands:\n"
                "/task <desc> — Submit a task\n"
                "/status — Daemon status\n"
                "/ping — Am I alive?\n"
                "/help — All commands\n\n"
                "Or just send a message to chat with the AI."
            )

            # Send with inline buttons on Telegram
            if msg.platform == Platform.TELEGRAM:
                tg = self.adapters.get(Platform.TELEGRAM)
                if tg and hasattr(tg, "send_with_buttons"):
                    buttons = [
                        [{"text": "📊 Status", "callback_data": "/status"},
                         {"text": "💰 Usage", "callback_data": "/usage"}],
                        [{"text": "📋 Jobs", "callback_data": "/jobs"},
                         {"text": "🏓 Ping", "callback_data": "/ping"}],
                    ]
                    await tg.send_with_buttons(
                        chat_id=msg.chat_id, text=welcome, buttons=buttons,
                    )
                    return None  # Already sent
            return welcome

        if text == "/stop":
            self.unregister_chat(msg.platform, msg.chat_id)
            return "👋 Notifications disabled. Send /start to re-enable."

        if text == "/ping":
            uptime_str = ""
            try:
                from unclaude.autonomous.daemon import AgentDaemon
                status = AgentDaemon.read_status()
                if status and status.get("started_at"):
                    uptime_sec = time.time() - status["started_at"]
                    hours = int(uptime_sec // 3600)
                    mins = int((uptime_sec % 3600) // 60)
                    uptime_str = f" | Up {hours}h {mins}m"
            except Exception:
                pass
            return f"🏓 *Pong!* I'm alive{uptime_str}"

        if text == "/models":
            try:
                from unclaude.config import get_settings
                settings = get_settings()
                lines = ["🧠 *Configured Models*\n"]
                default = settings.default_provider
                for name, pconfig in settings.providers.items():
                    marker = " ← active" if name == default else ""
                    lines.append(f"• `{name}`: {pconfig.model}{marker}")
                if not settings.providers:
                    lines.append("No providers configured yet.")
                return "\n".join(lines)
            except Exception as e:
                return f"Could not load model config: {e}"

        if text == "/budget":
            try:
                from unclaude.usage import get_usage_tracker
                tracker = get_usage_tracker()
                budget = tracker.get_budget()
                summary = tracker.get_summary(period="today")
                if not budget:
                    return (
                        f"💰 *No budget set*\n\n"
                        f"Today's spend: ${summary.total_cost_usd:.4f}\n"
                        f"Set one with: `unclaude usage budget --set 5.00`"
                    )
                pct = (summary.total_cost_usd /
                       budget["limit"]) * 100 if budget["limit"] > 0 else 0
                bar_filled = int(pct / 10)
                bar = "█" * bar_filled + "░" * (10 - bar_filled)
                return (
                    f"💰 *Budget Status*\n\n"
                    f"Spent: ${summary.total_cost_usd:.4f} / ${budget['limit']:.2f}\n"
                    f"[{bar}] {pct:.0f}%\n"
                    f"Requests today: {summary.total_requests}\n"
                    f"Action at limit: {budget.get('action', 'warn')}"
                )
            except Exception as e:
                return f"Could not load budget info: {e}"

        if text == "/kill":
            # Only allow owner to kill
            owner = self._owner_chat_ids.get(msg.platform)
            if owner and msg.chat_id != owner:
                return "⛔ Only the owner can stop the daemon."
            try:
                from unclaude.autonomous.daemon import AgentDaemon
                if not AgentDaemon.is_running():
                    return "⚪ Daemon is not running."
                AgentDaemon.stop_daemon()
                return "🛑 *Daemon stop signal sent.* It will shut down gracefully."
            except Exception as e:
                return f"❌ Failed to stop daemon: {e}"

        if text == "/help":
            return (
                "🤖 *UnClaude Commands*\n\n"
                "📋 *Tasks & Status*\n"
                "/task <desc> — Submit a task\n"
                "/jobs — List recent tasks\n"
                "/status — Daemon status\n"
                "/ping — Quick alive check\n\n"
                "💰 *Usage & Budget*\n"
                "/usage — Today's token usage\n"
                "/budget — Budget status\n"
                "/models — Configured models\n\n"
                "⚙️ *Control*\n"
                "/kill — Stop daemon remotely\n"
                "/clear — Reset chat history\n"
                "/stop — Disable notifications\n\n"
                "💬 Or just send a message to chat with the AI!"
            )

        if text == "/clear":
            if self._message_handler and hasattr(self._message_handler, "clear_history"):
                self._message_handler.clear_history(msg.chat_id)
            return "🧹 Chat history cleared. Fresh start!"

        if text == "/status":
            from unclaude.autonomous.daemon import AgentDaemon
            status = AgentDaemon.read_status()
            if not status:
                return "⚪ Agent daemon is *not running*.\n\nStart it with `unclaude agent start`"

            uptime_sec = time.time() - status.get("started_at", time.time())
            hours = int(uptime_sec // 3600)
            mins = int((uptime_sec % 3600) // 60)

            return (
                f"🟢 Agent daemon is *{status['status']}*\n\n"
                f"⏱ Uptime: {hours}h {mins}m\n"
                f"✅ Completed: {status.get('tasks_completed', 0)}\n"
                f"❌ Failed: {status.get('tasks_failed', 0)}\n"
                f"📋 Pending: {status.get('queue_pending', 0)}\n"
                f"💰 Total cost: ${status.get('total_cost_usd', 0):.4f}"
            )

        if text == "/usage":
            try:
                from unclaude.usage import get_usage_tracker
                tracker = get_usage_tracker()
                summary = tracker.get_summary(period="today")
                return (
                    f"📊 *Usage Today*\n\n"
                    f"Requests: {summary.total_requests}\n"
                    f"Tokens: {summary.total_tokens:,}\n"
                    f"Cost: ${summary.total_cost_usd:.4f}\n"
                    f"Models: {summary.unique_models}"
                )
            except Exception:
                return "Could not load usage data."

        if text == "/jobs":
            from unclaude.autonomous.daemon import TaskQueue
            queue = TaskQueue()
            tasks = queue.list_tasks(limit=5)
            if not tasks:
                return "📋 No tasks found."
            lines = ["📋 *Recent Tasks*\n"]
            for t in tasks:
                icon = {"completed": "✅", "failed": "❌", "running": "🔄", "queued": "⏳"}.get(
                    t.status.value, "❓"
                )
                lines.append(f"{icon} `{t.task_id}` {t.description[:60]}")
            return "\n".join(lines)

        if text.startswith("/task "):
            task_desc = text[6:].strip()
            if not task_desc:
                return "Usage: /task <description>\n\nExample: /task Fix the login bug in auth.py"
            try:
                from unclaude.autonomous.daemon import AgentDaemon
                status = AgentDaemon.read_status()
                if not status or status.get("status") == "stopped":
                    return (
                        "⚠️ Agent daemon is not running.\n"
                        "Start it with `unclaude agent start` first."
                    )

                from unclaude.autonomous.daemon import TaskQueue
                queue = TaskQueue()
                from unclaude.autonomous.daemon import DaemonTask
                task = DaemonTask(
                    description=task_desc,
                    source=f"messaging:{msg.platform.value}",
                    project_path="",
                )
                task_id = queue.push(task)
                return (
                    f"📥 *Task submitted!*\n\n"
                    f"*ID:* `{task_id}`\n"
                    f"*Task:* {task_desc[:200]}\n\n"
                    f"I'll notify you when it's done."
                )
            except Exception as e:
                return f"❌ Failed to submit task: {e}"

        # ── Free-form chat ──────────────────────────

        # If auto-registered just now, send a welcome first
        if newly_registered:
            welcome = (
                "👋 *Hey! I'm UnClaude.*\n\n"
                "I auto-registered you for notifications.\n"
                "Send /help to see what I can do, or just chat!"
            )
            adapter = self.adapters.get(msg.platform)
            if adapter and adapter.is_configured():
                await adapter.send(OutgoingMessage(
                    platform=msg.platform,
                    chat_id=msg.chat_id,
                    text=welcome,
                ))

        if self._message_handler:
            try:
                response = await self._message_handler(msg)
                return response
            except Exception as e:
                logger.error(f"Message handler error: {e}")
                return f"Error processing your message: {e}"

        return (
            "I received your message but the AI chat handler isn't active.\n"
            "Use /task <description> to submit tasks, or /help for commands."
        )

    async def process_and_reply(self, msg: IncomingMessage) -> None:
        """Handle an incoming message and send the reply back."""
        response = await self.handle_incoming(msg)
        if response:
            adapter = self.adapters.get(msg.platform)
            if adapter and adapter.is_configured():
                await adapter.send(OutgoingMessage(
                    platform=msg.platform,
                    chat_id=msg.chat_id,
                    text=response,
                    reply_to_message_id=msg.message_id,
                ))

    async def close(self) -> None:
        """Close all adapter connections."""
        for adapter in self.adapters.values():
            if hasattr(adapter, "close"):
                await adapter.close()


# ── Helpers ─────────────────────────────────────────────

def _split_message(text: str, max_len: int = 4000) -> list[str]:
    """Split a long message into chunks, trying to break at newlines."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break

        # Try to find a good break point
        break_at = text.rfind("\n", 0, max_len)
        if break_at < max_len // 2:
            break_at = text.rfind(" ", 0, max_len)
        if break_at < max_len // 2:
            break_at = max_len

        chunks.append(text[:break_at])
        text = text[break_at:].lstrip()

    return chunks


# ── Built-in LLM Chat Handler ──────────────────────────

class TelegramChatHandler:
    """Handles free-form chat messages by calling the configured LLM.

    Keeps per-chat conversation history so the bot maintains context.
    History is capped to avoid token blowup.
    """

    SYSTEM_PROMPT = (
        "You are UnClaude, an AI coding assistant available via Telegram. "
        "You help users with programming questions, code review, debugging, "
        "and general tech discussions. Keep responses concise and Telegram-friendly "
        "(use Markdown sparingly — bold with *, code with `backticks`). "
        "If the user wants you to perform a coding task on their project, "
        "suggest they use /task <description> to submit it to the agent daemon."
    )

    def __init__(self, max_history: int = 20):
        self._histories: dict[str, list[dict[str, str]]] = {}
        self._max_history = max_history
        self._provider = None

    def _get_provider(self):
        """Lazy-load the LLM provider with a fast model for Telegram chat."""
        if self._provider is None:
            from unclaude.providers.llm import Provider
            from unclaude.config import ProviderConfig
            self._provider = Provider()
            # Override to use flash model for fast Telegram responses
            # (thinking models like 2.5-pro take 30+ seconds, too slow for chat)
            if 'pro' in self._provider.config.model or '2.5' in self._provider.config.model:
                self._provider.config = ProviderConfig(
                    model='gemini-2.0-flash',
                    api_key=self._provider.config.api_key,
                    base_url=self._provider.config.base_url,
                    provider=self._provider.config.provider,
                )
            self._provider._request_type = "telegram_chat"
        return self._provider

    def _get_history(self, chat_id: str) -> list[dict[str, str]]:
        """Get or create conversation history for a chat."""
        if chat_id not in self._histories:
            self._histories[chat_id] = []
        return self._histories[chat_id]

    def _trim_history(self, history: list[dict[str, str]]) -> None:
        """Keep history under the max to avoid token blowup."""
        while len(history) > self._max_history * 2:
            # Remove oldest user+assistant pair
            history.pop(0)
            if history:
                history.pop(0)

    async def __call__(self, msg: IncomingMessage) -> str | None:
        """Handle a free-form message by chatting with the LLM."""
        provider = self._get_provider()
        history = self._get_history(msg.chat_id)

        # Add user message
        history.append({"role": "user", "content": msg.text})
        self._trim_history(history)

        # Build messages for the LLM
        from unclaude.providers.llm import Message

        messages = [Message(role="system", content=self.SYSTEM_PROMPT)]
        for h in history:
            messages.append(Message(role=h["role"], content=h["content"]))

        try:
            response = await provider.chat(
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
            )
            reply = response.content or "I couldn't generate a response."

            # Save assistant reply to history
            history.append({"role": "assistant", "content": reply})
            self._trim_history(history)

            return reply
        except Exception as e:
            logger.error(f"LLM chat error: {e}")
            # Remove the failed user message from history
            if history and history[-1]["role"] == "user":
                history.pop()
            return f"⚠️ LLM error: {e}\n\nYou can still use /task, /status, /help commands."

    def clear_history(self, chat_id: str) -> None:
        """Clear conversation history for a chat."""
        self._histories.pop(chat_id, None)


def create_chat_handler() -> TelegramChatHandler:
    """Create and return a chat handler instance."""
    return TelegramChatHandler()


# ── Singleton ───────────────────────────────────────────

_messenger: Messenger | None = None


def get_messenger() -> Messenger:
    """Get the global Messenger instance."""
    global _messenger
    if _messenger is None:
        _messenger = Messenger()
    return _messenger
