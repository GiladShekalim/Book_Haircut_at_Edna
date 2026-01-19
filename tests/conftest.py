import datetime
import os
from typing import List, Tuple
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import calendar as cal
from app import db
from app import main
from app import models, wa_client


@pytest.fixture(scope="session", autouse=True)
def set_test_env():
    os.environ.setdefault("TZ", "Asia/Jerusalem")
    os.environ.setdefault("DB_URL", "sqlite:///:memory:")
    os.environ.setdefault("WA_TOKEN", "test")
    os.environ.setdefault("PHONE_ID", "test")
    yield


@pytest.fixture(scope="session")
def tz():
    return ZoneInfo(os.getenv("TZ", "Asia/Jerusalem"))


@pytest.fixture(scope="session")
def test_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        future=True,
    )
    models.Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def TestingSessionLocal(test_engine):
    return sessionmaker(bind=test_engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture(autouse=True)
def override_db(test_engine, TestingSessionLocal, monkeypatch):
    db.engine = test_engine
    db.SessionLocal = TestingSessionLocal
    yield


@pytest.fixture
def db_session(TestingSessionLocal):
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def captured_messages(monkeypatch) -> List[Tuple[str, str]]:
    sent: List[Tuple[str, str]] = []

    def fake_send_text(to: str, text: str) -> None:
        sent.append(("text", text))

    def fake_send_buttons(to: str, prompt: str, buttons):
        sent.append(("buttons", prompt))

    monkeypatch.setattr(wa_client, "send_text", fake_send_text)
    monkeypatch.setattr(wa_client, "send_buttons", fake_send_buttons)
    return sent


@pytest.fixture
def calendar_stubs(monkeypatch, tz):
    base = datetime.datetime(2025, 1, 1, 10, 0, tzinfo=tz)
    slots = [base, base + datetime.timedelta(hours=2), base + datetime.timedelta(hours=4)]

    monkeypatch.setattr(cal, "find_next_slots", lambda **kwargs: slots)
    monkeypatch.setattr(cal, "is_slot_free", lambda start_time, duration_minutes=60, tz=None: True)

    def fake_create(summary, start_time, duration_minutes, user_phone, contact_name, note, tz):
        return {"htmlLink": "https://calendar.test/event"}

    monkeypatch.setattr(cal, "create_appointment", fake_create)
    return slots


@pytest.fixture
def client(override_db, calendar_stubs):
    with TestClient(main.app) as c:
        yield c
