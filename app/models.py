import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class PendingState(Base):
    __tablename__ = "pending_state"

    phone = Column(String(32), primary_key=True, index=True)
    slot_iso = Column(String(64), nullable=False)  # store ISO string to avoid tz loss in some DBs
    contact_name = Column(String(128), nullable=True)
    note = Column(String(512), nullable=True)
    step = Column(String(32), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "phone": self.phone,
            "slot_iso": self.slot_iso,
            "contact_name": self.contact_name,
            "note": self.note,
            "step": self.step,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
        }
