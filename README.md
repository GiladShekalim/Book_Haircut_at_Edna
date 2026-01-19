# Edna Hairdresser WhatsApp Bot (FastAPI + Google Calendar)

WhatsApp Cloud API bot that lets clients pick a slot, collects optional notes, writes confirmed appointments to Google Calendar, and notifies Edna.

## Prerequisites
- Python 3.11+
- WhatsApp Cloud API phone number ID + access token
- Google Calendar API enabled with a **service account** that has access to Edna’s calendar (JSON key file)
- Postgres (recommended) or SQLite for session/state storage
- Public HTTPS endpoint for the webhook (e.g., ngrok)

## Setup
1) Install deps:
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
2) Copy `env.example` to `.env` (or set env vars in your host) and fill values:
- WhatsApp: `WA_TOKEN`, `PHONE_ID`, `VERIFY_TOKEN`
- Calendar: `CALENDAR_ID`, `SA_CREDS_PATH`, optional `CALENDAR_DELEGATED_USER` (if impersonating)
- DB: `DB_URL` (e.g., `postgresql+psycopg2://user:pass@host:5432/dbname` or default `sqlite:///./edna.db`)
- Bot behavior: `TZ`, `WORK_START_HOUR`, `WORK_END_HOUR`, `SLOT_MINUTES`, `LOOKAHEAD_DAYS`, `MAX_SLOTS`, `PENDING_TTL_MINUTES`
- Optional: `EDNA_CONTROL_PHONE`, `WA_MAX_RETRIES`, `WA_BACKOFF_SECONDS`

3) Run locally:
```
uvicorn app.main:app --reload --port 5000
```
Or use the helper script on Windows:
```
scripts\run_dev.ps1
```
Expose via ngrok:
```
ngrok http 5000
```
Use the https URL as the Meta Webhook callback, verify with `VERIFY_TOKEN`, subscribe to `messages`.

4) Google Calendar auth:
- Place your service account JSON key at `SA_CREDS_PATH` (default `service-account.json`).
- Grant the service account access to the target calendar (share the calendar with the SA email). If using domain-wide delegation, set `CALENDAR_DELEGATED_USER` to impersonate Edna’s account.

## Webhook behavior
- `GET /webhook`: Meta verification using `hub.verify_token`.
- `POST /webhook`: Handles incoming messages and button replies:
  - Menu → “Book appointment”
  - Shows next free slots (business hours, skips Fri/Sat by default)
  - Collects optional notes
  - Confirm/Cancel buttons
  - On confirm: creates Calendar event and sends confirmation; optionally notifies Edna’s number.
- Health: `GET /health/live` (process up), `GET /health/ready` (DB reachable)

## Files
- `app/main.py` – FastAPI webhook + conversation flow
- `app/wa_client.py` – WhatsApp Cloud API send helpers (text, buttons)
- `app/calendar.py` – Google Calendar free/busy lookup and event creation (service account)
- `app/state.py` – DB-backed pending slot + note tracking
- `app/db.py`, `app/models.py` – DB engine/session and schema
- `requirements.txt` – dependencies
- `env.example` – environment variable template
- `scripts/run_dev.ps1` – quick dev server bootstrap on Windows

## Notes
- Timezone defaults to `Asia/Jerusalem`.
- Work window defaults to 09:00–17:00, 60-minute slots, 7-day lookahead, skipping Fri/Sat.
- Pending sessions expire after `PENDING_TTL_MINUTES` (default 30). Cleaned per request.
- DB schema auto-creates on startup. For Postgres, ensure the database exists and `DB_URL` is correct.
- Logs are JSON-formatted to stdout; useful for shipping to log aggregators.

Notes:
Added production-friendly health checks, structured logging, and a simple run script, plus deployment guidance.
Changes made
Structured JSON logging: configured via python-json-logger (stdout) in app/main.py.
Health endpoints: GET /health/live (process up) and GET /health/ready (DB ping).
Added run helper: scripts/run_dev.ps1 to create venv, install deps, and start uvicorn on Windows.
Docs updated: README.md now lists the health endpoints, run script, and logging note.
Dependency added: python-json-logger in requirements.txt.
Step-by-step deployment (beginner-friendly)
1) Clone and open repo:
git clone ... then cd BookanAppointment
2) Set up Python + venv:
python -m venv .venv
Windows: .venv\Scripts\activate
Install deps: pip install -r requirements.txt
3) Configure environment:
Copy env.example to .env (or set env vars directly).
Fill:
WhatsApp: WA_TOKEN, PHONE_ID, VERIFY_TOKEN
Calendar: CALENDAR_ID, SA_CREDS_PATH (path to service account JSON), optional CALENDAR_DELEGATED_USER
DB: DB_URL (e.g., Postgres URL; SQLite default also works)
Bot: TZ, WORK_START_HOUR, WORK_END_HOUR, SLOT_MINUTES, LOOKAHEAD_DAYS, MAX_SLOTS, PENDING_TTL_MINUTES
Optional: EDNA_CONTROL_PHONE, WA_MAX_RETRIES, WA_BACKOFF_SECONDS
4) Google Calendar setup:
Create/download a service account key JSON; save to SA_CREDS_PATH (e.g., service-account.json in project root).
Share Edna’s calendar with the service account email (or set CALENDAR_DELEGATED_USER if using domain delegation).
Set CALENDAR_ID (e.g., primary or a specific calendar ID).
5) Database:
For Postgres, create the database and user; set DB_URL.
First app start will auto-create the pending_state table.
6) Run locally:
Windows helper: scripts\run_dev.ps1
Or: uvicorn app.main:app --reload --host 0.0.0.0 --port 5000
7) Expose webhook (dev):
ngrok http 5000
Use the HTTPS URL in WhatsApp Cloud webhook settings; set verify token to VERIFY_TOKEN; subscribe to messages.
8) Verify health:
GET http://localhost:5000/health/live → should return {"status": "ok"}
GET http://localhost:5000/health/ready → should return {"status": "ok"} (checks DB)
9) Connect WhatsApp Cloud:
Ensure WA_TOKEN is valid (not sandbox), PHONE_ID matches your number.
Send a test message to your business number; the webhook should handle it.
10) Run tests (optional but recommended):
pytest
Execution script provided
scripts/run_dev.ps1 automates venv creation, dependency install, and starting uvicorn on port 5000.