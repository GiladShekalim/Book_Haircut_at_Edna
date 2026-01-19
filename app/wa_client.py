import logging
import os
import time
from typing import Dict, List

import requests

logger = logging.getLogger(__name__)

WA_TOKEN = os.getenv("WA_TOKEN", "")
PHONE_ID = os.getenv("PHONE_ID", "")

API_URL = f"https://graph.facebook.com/v18.0/{PHONE_ID}/messages"
HEADERS = {
    "Authorization": f"Bearer {WA_TOKEN}",
    "Content-Type": "application/json",
}

MAX_RETRIES = int(os.getenv("WA_MAX_RETRIES", "3"))
BACKOFF_SECONDS = float(os.getenv("WA_BACKOFF_SECONDS", "1.5"))


def _post(payload: Dict) -> None:
    if not WA_TOKEN or not PHONE_ID:
        logger.warning("WhatsApp credentials missing. Skipping send. Payload=%s", payload)
        return
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(API_URL, headers=HEADERS, json=payload, timeout=10)
            if resp.ok:
                return
            is_retryable = resp.status_code >= 500
            logger.error("WhatsApp send failed (attempt %s): %s %s", attempt, resp.status_code, resp.text)
            if not is_retryable or attempt == MAX_RETRIES:
                return
        except requests.RequestException as exc:
            logger.error("WhatsApp send exception (attempt %s): %s", attempt, exc)
            if attempt == MAX_RETRIES:
                return
        time.sleep(BACKOFF_SECONDS * attempt)


def send_text(to: str, text: str) -> None:
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text[:1024]},
    }
    _post(payload)


def send_buttons(to: str, prompt: str, buttons: List[Dict[str, str]]) -> None:
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": prompt[:1024]},
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": b["id"], "title": b["title"][:20]},
                    }
                    for b in buttons
                ][:3],  # WA supports up to 3 buttons
            },
        },
    }
    _post(payload)
