import datetime
from zoneinfo import ZoneInfo


def _text_payload(body: str, sender: str = "111", name: str = "Test User"):
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": sender,
                                    "id": "wamid.test",
                                    "timestamp": "1234567890",
                                    "type": "text",
                                    "text": {"body": body},
                                }
                            ],
                            "contacts": [{"profile": {"name": name}}],
                        }
                    }
                ]
            }
        ]
    }


def _button_payload(btn_id: str, sender: str = "111", name: str = "Test User"):
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": sender,
                                    "id": "wamid.button",
                                    "timestamp": "1234567890",
                                    "type": "interactive",
                                    "interactive": {"button_reply": {"id": btn_id, "title": "btn"}},
                                }
                            ],
                            "contacts": [{"profile": {"name": name}}],
                        }
                    }
                ]
            }
        ]
    }


def test_full_booking_flow(client, calendar_stubs, captured_messages):
    # Step 1: user asks to book
    resp = client.post("/webhook", json=_text_payload("book appointment"))
    assert resp.status_code == 200
    assert resp.json()["status"] == "menu_sent"
    assert any(kind == "buttons" for kind, _ in captured_messages)

    # Step 2: user selects a slot
    slot_iso = calendar_stubs[0].isoformat()
    resp = client.post("/webhook", json=_button_payload(f"slot::{slot_iso}"))
    assert resp.status_code == 200
    assert resp.json()["status"] == "awaiting_note"

    # Step 3: user adds a note
    resp = client.post("/webhook", json=_text_payload("bring color"))
    assert resp.status_code == 200
    assert resp.json()["status"] == "note_recorded"
    # Should have sent a confirmation prompt
    assert any("Confirm appointment" in text for kind, text in captured_messages if kind == "buttons")

    # Step 4: user confirms
    resp = client.post("/webhook", json=_button_payload(f"confirm::{slot_iso}"))
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"
    assert any("Confirmed" in text for kind, text in captured_messages if kind == "text")


def test_stale_confirm_returns_menu(client, captured_messages):
    tz = ZoneInfo("Asia/Jerusalem")
    slot_iso = datetime.datetime(2025, 1, 1, 12, 0, tzinfo=tz).isoformat()
    # Confirm without pending session -> should prompt new menu
    resp = client.post("/webhook", json=_button_payload(f"confirm::{slot_iso}", sender="999"))
    assert resp.status_code == 200
    assert resp.json()["status"] == "stale_pending"
    assert any(kind == "buttons" for kind, _ in captured_messages)
