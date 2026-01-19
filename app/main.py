import datetime
import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from pythonjsonlogger import jsonlogger
from sqlalchemy import text
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo

from app import calendar as cal
from app import db
from app import state
from app import wa_client

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    # Running without python-dotenv (production containers) is fine
    pass

_root_logger = logging.getLogger()
if not _root_logger.handlers:
    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"levelname": "level"},
    )
    handler.setFormatter(formatter)
    _root_logger.addHandler(handler)
_root_logger.setLevel(logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Edna Hairdresser WhatsApp Bot")

# --- Configuration ---
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "change_me")
EDNA_CONTROL_PHONE = os.getenv("EDNA_CONTROL_PHONE")  # Optional: send Edna a notification
TIMEZONE = ZoneInfo(os.getenv("TZ", "Asia/Jerusalem"))

# Working hours defaults (24h clock)
WORK_START_HOUR = int(os.getenv("WORK_START_HOUR", "9"))
WORK_END_HOUR = int(os.getenv("WORK_END_HOUR", "17"))
SLOT_MINUTES = int(os.getenv("SLOT_MINUTES", "60"))
LOOKAHEAD_DAYS = int(os.getenv("LOOKAHEAD_DAYS", "7"))
MAX_SLOTS = int(os.getenv("MAX_SLOTS", "6"))


# --- Helpers ---
def _as_tz(dt: datetime.datetime) -> datetime.datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=TIMEZONE)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


@app.get("/health/live")
async def health_live() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready(session: Session = Depends(db.get_session)) -> Dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:
        logger.exception("Readiness check failed: %s", exc)
        raise HTTPException(status_code=503, detail="not ready")


def _send_menu(to: str) -> None:
    wa_client.send_buttons(
        to=to,
        prompt="Welcome to Edna Hairdresser! What would you like to do?",
        buttons=[
            {"id": "menu_book", "title": "Book appointment"},
            {"id": "menu_help", "title": "Help"},
        ],
    )


def _send_slots(to: str, contact_name: Optional[str]) -> Optional[List[datetime.datetime]]:
    try:
        slots = cal.find_next_slots(
            tz=TIMEZONE,
            work_start_hour=WORK_START_HOUR,
            work_end_hour=WORK_END_HOUR,
            slot_minutes=SLOT_MINUTES,
            lookahead_days=LOOKAHEAD_DAYS,
            max_slots=MAX_SLOTS,
        )
    except Exception as exc:
        logger.exception("Failed to compute slots: %s", exc)
        wa_client.send_text(to, "Sorry, I couldn't load available times right now. Please try again soon.")
        return None

    if not slots:
        wa_client.send_text(
            to,
            "Sorry, no open slots found in the next few days. Please try a different time.",
        )
        return None

    human = contact_name or "there"
    wa_client.send_buttons(
        to=to,
        prompt=f"Hi {human}, pick a time that works for you:",
        buttons=[
            {
                "id": f"slot::{slot.isoformat()}",
                "title": slot.astimezone(TIMEZONE).strftime("%a %d/%m %H:%M"),
            }
            for slot in slots[:3]
        ],
    )
    return slots


def _send_confirmation(to: str, slot: datetime.datetime, note: Optional[str]) -> None:
    display = slot.astimezone(TIMEZONE).strftime("%A %d/%m at %H:%M")
    text_note = f"\nNotes: {note}" if note else ""
    wa_client.send_buttons(
        to=to,
        prompt=f"Confirm appointment on {display}?{text_note}",
        buttons=[
            {"id": f"confirm::{slot.isoformat()}", "title": "✅ Confirm"},
            {"id": "cancel_flow", "title": "❌ Cancel"},
        ],
    )


def _notify_edna(user_phone: str, contact_name: Optional[str], slot: datetime.datetime, note: Optional[str]) -> None:
    if not EDNA_CONTROL_PHONE:
        return
    display = slot.astimezone(TIMEZONE).strftime("%A %d/%m %H:%M")
    note_line = f"\nNotes: {note}" if note else ""
    wa_client.send_text(
        EDNA_CONTROL_PHONE,
        f"New appointment request confirmed:\n"
        f"Client: {contact_name or 'Unknown'}\n"
        f"Phone: {user_phone}\n"
        f"When: {display}{note_line}",
    )


# --- Routes ---
@app.get("/webhook")
async def verify_webhook(mode: str = "", hub_verify_token: str = "", hub_challenge: str = ""):
    # Meta sends hub.* query params; FastAPI maps unknown params to default "".
    if mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return hub_challenge
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
async def whatsapp_webhook(request: Request, session: Session = Depends(db.get_session)) -> Dict[str, Any]:
    payload = await request.json()
    logger.debug("Incoming payload: %s", payload)

    entry = (
        payload.get("entry", [{}])[0]
        .get("changes", [{}])[0]
        .get("value", {})
    )

    if "messages" not in entry:
        return {"status": "ignored"}

    message = entry["messages"][0]
    sender = message.get("from")
    contact_name = None
    contacts = entry.get("contacts", [])
    if contacts:
        contact_name = contacts[0].get("profile", {}).get("name")

    if not sender:
        return {"status": "ignored"}

    msg_type = message.get("type")

    # Handle interactive button replies
    if msg_type == "interactive":
        button = message.get("interactive", {}).get("button_reply", {})
        btn_id = button.get("id")

        if not btn_id:
            return {"status": "ignored"}

        if btn_id == "menu_book":
            _send_slots(sender, contact_name)
            return {"status": "menu_sent"}

        if btn_id == "menu_help":
            wa_client.send_text(sender, "To book, choose 'Book appointment' and pick a time.")
            return {"status": "help_sent"}

        if btn_id.startswith("slot::"):
            iso_time = btn_id.split("slot::", maxsplit=1)[1]
            try:
                slot_dt = datetime.datetime.fromisoformat(iso_time)
                slot_dt = _as_tz(slot_dt)
            except Exception:
                wa_client.send_text(sender, "Could not parse that slot. Please try again.")
                return {"status": "invalid_slot"}

            # Save pending slot and ask for notes
            state.set_pending_slot(session, sender, slot_dt, contact_name, TIMEZONE)
            display = slot_dt.astimezone(TIMEZONE).strftime("%A %d/%m at %H:%M")
            wa_client.send_text(
                sender,
                f"Great, penciled {display}. Any notes for Edna? Reply with text or type 'skip'.",
            )
            return {"status": "awaiting_note"}

        if btn_id.startswith("confirm::"):
            iso_time = btn_id.split("confirm::", maxsplit=1)[1]
            pending = state.get_pending(session, sender, TIMEZONE)
            try:
                slot_dt = datetime.datetime.fromisoformat(iso_time)
                slot_dt = _as_tz(slot_dt)
            except Exception:
                wa_client.send_text(sender, "Could not parse the confirmation slot. Please try again.")
                return {"status": "invalid_confirm_slot"}

            if not pending or pending.slot.isoformat() != slot_dt.isoformat():
                wa_client.send_text(sender, "This slot is no longer pending. Please pick a time again.")
                _send_menu(sender)
                return {"status": "stale_pending"}

            if not cal.is_slot_free(slot_dt, duration_minutes=SLOT_MINUTES, tz=TIMEZONE):
                wa_client.send_text(sender, "Sorry, that slot was just taken. Please pick another time.")
                _send_slots(sender, contact_name)
                state.clear(session, sender)
                return {"status": "slot_busy"}

            event = cal.create_appointment(
                summary="Hair appointment",
                start_time=slot_dt,
                duration_minutes=SLOT_MINUTES,
                user_phone=sender,
                contact_name=contact_name,
                note=pending.note,
                tz=TIMEZONE,
            )

            wa_client.send_text(
                sender,
                f"Confirmed! See you then.\nCalendar link: {event.get('htmlLink', 'created')}",
            )
            _notify_edna(sender, contact_name, slot_dt, pending.note)
            state.clear(session, sender)
            return {"status": "confirmed"}

        if btn_id == "cancel_flow":
            state.clear(session, sender)
            wa_client.send_text(sender, "Booking cancelled. You can start again anytime.")
            return {"status": "cancelled"}

        wa_client.send_text(sender, "Sorry, I didn't recognize that button.")
        return {"status": "unknown_button"}

    # Handle plain text messages
    if msg_type == "text":
        text_body = message.get("text", {}).get("body", "").strip()
        pending = state.get_pending(session, sender, TIMEZONE)

        if pending and pending.step == "awaiting_note":
            note = "" if text_body.lower() == "skip" else text_body
            pending_with_note = state.set_note(session, sender, note, TIMEZONE)
            if not pending_with_note:
                wa_client.send_text(sender, "Your session expired. Please pick a time again.")
                _send_menu(sender)
                return {"status": "pending_missing"}
            _send_confirmation(sender, pending.slot, note)
            return {"status": "note_recorded"}

        lowered = text_body.lower()
        if "book" in lowered or "appointment" in lowered or "hair" in lowered:
            _send_menu(sender)
            return {"status": "menu_sent"}

        wa_client.send_text(
            sender,
            "Hi! I can book your appointment at Edna Hairdresser.\nChoose an option:",
        )
        _send_menu(sender)
        return {"status": "menu_sent"}

    wa_client.send_text(sender, "Unsupported message type. Please use the menu buttons.")
    return {"status": "unsupported"}
