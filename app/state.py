import datetime
import os
from dataclasses import dataclass
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import PendingState as PendingStateModel

PENDING_TTL_MINUTES = int(os.getenv("PENDING_TTL_MINUTES", "30"))


@dataclass
class PendingRecord:
    phone: str
    slot: datetime.datetime
    contact_name: Optional[str]
    note: Optional[str]
    step: str


def _now(tz: ZoneInfo) -> datetime.datetime:
    return datetime.datetime.now(tz=tz)


def cleanup_expired(session: Session, tz: ZoneInfo) -> None:
    now = _now(tz)
    session.execute(delete(PendingStateModel).where(PendingStateModel.expires_at <= now))


def set_pending_slot(
    session: Session,
    user_phone: str,
    slot: datetime.datetime,
    contact_name: Optional[str],
    tz: ZoneInfo,
    ttl_minutes: Optional[int] = None,
) -> None:
    ttl = ttl_minutes or PENDING_TTL_MINUTES
    expires_at = _now(tz) + datetime.timedelta(minutes=ttl)
    slot_iso = slot.isoformat()
    existing = session.get(PendingStateModel, user_phone)
    if existing:
        existing.slot_iso = slot_iso
        existing.contact_name = contact_name
        existing.note = None
        existing.step = "awaiting_note"
        existing.expires_at = expires_at
    else:
        pending = PendingStateModel(
            phone=user_phone,
            slot_iso=slot_iso,
            contact_name=contact_name,
            note=None,
            step="awaiting_note",
            expires_at=expires_at,
        )
        session.add(pending)


def set_note(session: Session, user_phone: str, note: Optional[str], tz: ZoneInfo) -> Optional[PendingRecord]:
    record = session.get(PendingStateModel, user_phone)
    if not record:
        return None
    record.note = note
    record.step = "awaiting_confirm"
    record.expires_at = _now(tz) + datetime.timedelta(minutes=PENDING_TTL_MINUTES)
    return PendingRecord(
        phone=record.phone,
        slot=datetime.datetime.fromisoformat(record.slot_iso),
        contact_name=record.contact_name,
        note=record.note,
        step=record.step,
    )


def get_pending(session: Session, user_phone: str, tz: ZoneInfo) -> Optional[PendingRecord]:
    cleanup_expired(session, tz)
    stmt = select(PendingStateModel).where(PendingStateModel.phone == user_phone)
    result = session.scalars(stmt).first()
    if not result:
        return None
    try:
        slot_dt = datetime.datetime.fromisoformat(result.slot_iso)
    except Exception:
        clear(session, user_phone)
        return None
    return PendingRecord(
        phone=result.phone,
        slot=slot_dt,
        contact_name=result.contact_name,
        note=result.note,
        step=result.step,
    )


def clear(session: Session, user_phone: str) -> None:
    session.execute(delete(PendingStateModel).where(PendingStateModel.phone == user_phone))
