import datetime
import os
from typing import List, Optional
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CALENDAR_ID = os.getenv("CALENDAR_ID", "primary")
SA_CREDS_PATH = os.getenv("SA_CREDS_PATH", "service-account.json")
DELEGATED_USER = os.getenv("CALENDAR_DELEGATED_USER")


def _get_calendar_service():
    creds = service_account.Credentials.from_service_account_file(SA_CREDS_PATH, scopes=SCOPES)
    if DELEGATED_USER:
        creds = creds.with_subject(DELEGATED_USER)
    return build("calendar", "v3", credentials=creds)


def _ensure_tz(dt: datetime.datetime, tz: ZoneInfo) -> datetime.datetime:
    """Guarantee timezone-aware datetimes for Calendar API."""
    return dt if dt.tzinfo else dt.replace(tzinfo=tz)


def is_slot_free(start_time: datetime.datetime, duration_minutes: int = 60, tz: Optional[ZoneInfo] = None) -> bool:
    """Check if a given slot is free using Calendar freebusy."""
    tzinfo = tz or ZoneInfo(os.getenv("TZ", "UTC"))
    start_time = _ensure_tz(start_time, tzinfo)
    service = _get_calendar_service()
    end_time = start_time + datetime.timedelta(minutes=duration_minutes)

    body = {
        "timeMin": start_time.isoformat(),
        "timeMax": end_time.isoformat(),
        "items": [{"id": CALENDAR_ID}],
    }
    result = service.freebusy().query(body=body).execute()
    busy = result.get("calendars", {}).get(CALENDAR_ID, {}).get("busy", [])
    return len(busy) == 0


def find_next_slots(
    tz: ZoneInfo,
    work_start_hour: int,
    work_end_hour: int,
    slot_minutes: int,
    lookahead_days: int,
    max_slots: int = 6,
) -> List[datetime.datetime]:
    """Generate the next available slots within the work window."""
    now = datetime.datetime.now(tz=tz)
    slots: List[datetime.datetime] = []
    min_start = now + datetime.timedelta(minutes=30)

    for day_offset in range(lookahead_days):
        day = now.date() + datetime.timedelta(days=day_offset)
        # Skip Friday/Saturday by default (Israel weekend)
        if day.weekday() in (4, 5):
            continue

        day_start = datetime.datetime(
            year=day.year,
            month=day.month,
            day=day.day,
            hour=work_start_hour,
            minute=0,
            tzinfo=tz,
        )
        day_end = day_start.replace(hour=work_end_hour, minute=0)

        slot_dt = day_start
        step = datetime.timedelta(minutes=slot_minutes)
        while slot_dt < day_end:
            if slot_dt >= min_start and is_slot_free(slot_dt, duration_minutes=slot_minutes, tz=tz):
                slots.append(slot_dt)
                if len(slots) >= max_slots:
                    return slots
            slot_dt += step
    return slots


def create_appointment(
    summary: str,
    start_time: datetime.datetime,
    duration_minutes: int,
    user_phone: str,
    contact_name: Optional[str],
    note: Optional[str],
    tz: ZoneInfo,
):
    service = _get_calendar_service()
    start = _ensure_tz(start_time, tz)
    end = start + datetime.timedelta(minutes=duration_minutes)

    description_parts = [
        f"WhatsApp: {user_phone}",
    ]
    if contact_name:
        description_parts.append(f"Name: {contact_name}")
    if note:
        description_parts.append(f"Notes: {note}")

    event = {
        "summary": summary,
        "location": "Edna Hairdresser",
        "description": "\n".join(description_parts),
        "start": {"dateTime": start.isoformat(), "timeZone": str(tz)},
        "end": {"dateTime": end.isoformat(), "timeZone": str(tz)},
    }
    return service.events().insert(calendarId=CALENDAR_ID, body=event, sendUpdates="all").execute()
