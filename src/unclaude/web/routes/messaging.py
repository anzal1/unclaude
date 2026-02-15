"""Messaging API routes — webhooks for Telegram/WhatsApp + management endpoints."""

from fastapi import APIRouter, Request, HTTPException, Form
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


# ── Pydantic models ────────────────────────────────────

class TelegramSetup(BaseModel):
    bot_token: str


class WhatsAppSetup(BaseModel):
    account_sid: str
    auth_token: str
    from_number: str = "whatsapp:+14155238886"


class WebhookSetup(BaseModel):
    webhook_url: str
    secret: str = ""


class TestMessage(BaseModel):
    platform: str  # telegram, whatsapp, webhook
    chat_id: str
    text: str


# ── Webhook Endpoints (receive messages) ───────────────

@router.post("/messaging/telegram/webhook")
async def telegram_webhook(request: Request):
    """Receive updates from Telegram Bot API.

    Telegram sends POST requests here when the bot gets a message.
    Set this up via: POST /api/messaging/telegram/setup
    """
    from unclaude.messaging import get_messenger, Platform

    messenger = get_messenger()
    adapter = messenger.adapters.get(Platform.TELEGRAM)
    if not adapter:
        raise HTTPException(status_code=503, detail="Telegram not configured")

    payload = await request.json()
    msg = await adapter.handle_webhook(payload)
    if msg:
        await messenger.process_and_reply(msg)

    # Always return 200 to Telegram (otherwise it retries)
    return {"ok": True}


@router.post("/messaging/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    """Receive messages from Twilio WhatsApp.

    Twilio sends form-encoded POST requests here.
    """
    from unclaude.messaging import get_messenger, Platform

    messenger = get_messenger()
    adapter = messenger.adapters.get(Platform.WHATSAPP)
    if not adapter:
        raise HTTPException(status_code=503, detail="WhatsApp not configured")

    # Twilio sends form data, not JSON
    form_data = await request.form()
    payload = dict(form_data)
    msg = await adapter.handle_webhook(payload)
    if msg:
        await messenger.process_and_reply(msg)

    # Twilio expects TwiML response, but empty 200 works too
    return "<Response></Response>"


@router.post("/messaging/webhook/incoming")
async def generic_webhook(request: Request):
    """Receive messages from a generic webhook source."""
    from unclaude.messaging import get_messenger, Platform

    messenger = get_messenger()
    adapter = messenger.adapters.get(Platform.WEBHOOK)
    if not adapter:
        raise HTTPException(status_code=503, detail="Webhook not configured")

    payload = await request.json()
    msg = await adapter.handle_webhook(payload)
    if msg:
        await messenger.process_and_reply(msg)

    return {"ok": True}


# ── Setup Endpoints ────────────────────────────────────

@router.post("/messaging/telegram/setup")
async def setup_telegram(req: TelegramSetup, request: Request):
    """Configure Telegram bot integration."""
    from unclaude.messaging import get_messenger, TelegramAdapter

    messenger = get_messenger()
    messenger.configure_telegram(req.bot_token)

    # Verify the token by calling getMe
    adapter = messenger.adapters.get(
        messenger.adapters.__class__.__mro__[0])  # type: ignore
    tg = TelegramAdapter(bot_token=req.bot_token)
    bot_info = await tg.get_me()

    if not bot_info:
        return {
            "ok": False,
            "error": "Invalid bot token — could not reach Telegram API",
        }

    # Auto-set webhook to our endpoint
    base_url = str(request.base_url).rstrip("/")
    webhook_url = f"{base_url}/api/messaging/telegram/webhook"

    # Only set webhook if we have a public URL (not localhost)
    webhook_set = False
    if "localhost" not in base_url and "127.0.0.1" not in base_url:
        webhook_set = await tg.set_webhook(webhook_url)

    await tg.close()

    return {
        "ok": True,
        "bot": {
            "username": bot_info.get("username", "unknown"),
            "name": bot_info.get("first_name", "unknown"),
        },
        "webhook_set": webhook_set,
        "webhook_url": webhook_url,
        "note": (
            "Webhook registered!" if webhook_set
            else "Bot verified! Set the webhook manually if running behind a tunnel: "
                 f"POST to Telegram API with url={webhook_url}"
        ),
    }


@router.post("/messaging/whatsapp/setup")
async def setup_whatsapp(req: WhatsAppSetup):
    """Configure WhatsApp (Twilio) integration."""
    from unclaude.messaging import get_messenger

    messenger = get_messenger()
    messenger.configure_whatsapp(
        account_sid=req.account_sid,
        auth_token=req.auth_token,
        from_number=req.from_number,
    )

    return {
        "ok": True,
        "from_number": req.from_number,
        "note": (
            "WhatsApp configured! Set your Twilio webhook URL to: "
            "/api/messaging/whatsapp/webhook"
        ),
    }


@router.post("/messaging/webhook/setup")
async def setup_webhook(req: WebhookSetup):
    """Configure generic webhook integration."""
    from unclaude.messaging import get_messenger

    messenger = get_messenger()
    messenger.configure_webhook(
        webhook_url=req.webhook_url,
        secret=req.secret,
    )

    return {
        "ok": True,
        "webhook_url": req.webhook_url,
        "note": "Webhook configured! Send incoming messages to /api/messaging/webhook/incoming",
    }


# ── Status & Management ───────────────────────────────

@router.get("/messaging/status")
async def messaging_status():
    """Get the status of all messaging integrations."""
    from unclaude.messaging import get_messenger

    messenger = get_messenger()
    return messenger.get_status()


@router.post("/messaging/test")
async def test_message(req: TestMessage):
    """Send a test message to verify the integration works."""
    from unclaude.messaging import get_messenger, Platform

    messenger = get_messenger()

    try:
        platform = Platform(req.platform)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid platform: {req.platform}. Use: telegram, whatsapp, webhook",
        )

    adapter = messenger.adapters.get(platform)
    if not adapter or not adapter.is_configured():
        raise HTTPException(
            status_code=400,
            detail=f"{req.platform} is not configured. Set it up first.",
        )

    from unclaude.messaging import OutgoingMessage
    success = await adapter.send(OutgoingMessage(
        platform=platform,
        chat_id=req.chat_id,
        text=req.text,
    ))

    return {"ok": success, "platform": req.platform, "chat_id": req.chat_id}


@router.delete("/messaging/{platform_name}")
async def remove_integration(platform_name: str):
    """Remove a messaging integration."""
    from unclaude.messaging import get_messenger, Platform

    messenger = get_messenger()

    try:
        platform = Platform(platform_name)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Invalid platform: {platform_name}")

    if platform in messenger.adapters:
        adapter = messenger.adapters.pop(platform)
        if hasattr(adapter, "close"):
            await adapter.close()
        messenger._registered_chats[platform] = set()
        messenger._save_config()
        return {"ok": True, "removed": platform_name}

    return {"ok": False, "error": f"{platform_name} was not configured"}
