import datetime
from zoneinfo import ZoneInfo

from app import state


def test_state_set_and_expire(db_session, monkeypatch):
    tz = ZoneInfo("Asia/Jerusalem")
    base_time = datetime.datetime(2025, 1, 1, 9, 0, tzinfo=tz)

    monkeypatch.setattr(state, "_now", lambda tz: base_time)
    state.set_pending_slot(db_session, "123", base_time, contact_name="Alice", tz=tz, ttl_minutes=1)
    db_session.commit()

    pending = state.get_pending(db_session, "123", tz)
    assert pending is not None
    assert pending.contact_name == "Alice"

    # Advance time beyond TTL to trigger cleanup
    monkeypatch.setattr(state, "_now", lambda tz: base_time + datetime.timedelta(minutes=2))
    expired = state.get_pending(db_session, "123", tz)
    assert expired is None


def test_state_note_and_confirm_step(db_session, monkeypatch):
    tz = ZoneInfo("Asia/Jerusalem")
    slot_time = datetime.datetime(2025, 1, 1, 11, 0, tzinfo=tz)
    monkeypatch.setattr(state, "_now", lambda tz: slot_time)

    state.set_pending_slot(db_session, "555", slot_time, contact_name=None, tz=tz)
    db_session.commit()

    updated = state.set_note(db_session, "555", "bring color", tz)
    assert updated is not None
    assert updated.note == "bring color"
    assert updated.step == "awaiting_confirm"
