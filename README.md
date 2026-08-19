# FieldCheck AI

Automated industrial asset inspection platform. Field inspectors upload photos of equipment (pressure gauges, control valves, electrical panels, and similar assets); the system extracts OCR nameplate specs, detects visual defects, evaluates safety compliance, and generates an enterprise-ready HTML inspection report — all through an async API backed by a vision LLM (GPT-4o or Claude 3.5 Sonnet) with strict structured-output validation.

## Contents

- [Architecture](#architecture)
- [Quick start (local, no Docker)](#quick-start-local-no-docker)
- [Quick start (Docker Compose)](#quick-start-docker-compose)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [Running the demo pipeline](#running-the-demo-pipeline)
- [Running tests](#running-tests)
- [Security notes](#security-notes)
- [Project structure](#project-structure)
- [Email delivery & mobile login](#email-delivery--mobile-login)
- [Android app](#android-app)

## Architecture

```
Inspector's phone/browser
        │  drag & drop photo
        ▼
frontend/ (Tailwind + vanilla JS, served at /app or standalone)
        │  POST /api/v1/inspections/upload
        ▼
FastAPI (app/main.py)  ── validates + sanitizes file (storage_service.py)
        │  creates Inspection row, status=PENDING
        │  schedules async work (BackgroundTasks, or Celery if USE_CELERY=true)
        ▼
inspection_pipeline.py ── calls vision_engine.py (GPT-4o / Claude 3.5 Sonnet,
        │                  strict Pydantic structured-output validation, retries)
        ▼
SQLAlchemy 2.0 async ORM ── Inspection / Asset / Defect tables (SQLite or Postgres)
        │
        ▼
GET /api/v1/inspections/{id}          → poll status + full JSON payload
GET /api/v1/inspections/{id}/report   → clean HTML report (printable / PDF-able)
```

Async processing has two interchangeable backends:

- **FastAPI `BackgroundTasks`** (default, `USE_CELERY=false`) — runs the vision call in-process after the HTTP response is returned. Zero extra infrastructure; ideal for the MVP/demo.
- **Celery + Redis** (`USE_CELERY=true`) — offloads processing to a separate worker process via `app/services/celery_app.py`, for horizontal scale. `docker-compose.yml` includes a `worker` service (profile `celery`) for this path.

## Quick start (local, no Docker)

Requires Python 3.11+.

```bash
# 1. Clone/enter the project, create a virtualenv
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env: set VISION_PROVIDER, OPENAI_API_KEY or ANTHROPIC_API_KEY.
# Leave VISION_MOCK_MODE=true (default) to run the whole app with NO API
# key at all — a deterministic mock vision result is returned instead.

# 4. Run the API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Now open:

- **Dashboard UI:** http://localhost:8000/app/index.html
- **Interactive API docs (Swagger):** http://localhost:8000/api/docs
- **Health check:** http://localhost:8000/health

The SQLite database file (`fieldcheck.db`) and `uploads/` directory are created automatically on first run.

## Quick start (Docker Compose)

```bash
cp .env.example .env
# edit .env as needed

docker compose up --build
```

This starts:
- `redis` — message broker (used only if `USE_CELERY=true`)
- `api` — the FastAPI app on `http://localhost:8000`

To also run the Celery worker (distributed processing path):

```bash
# in .env, set USE_CELERY=true, then:
docker compose --profile celery up --build
```

## Configuration

All configuration lives in `.env` (see `.env.example` for the full annotated list). Key variables:

| Variable | Purpose |
|---|---|
| `VISION_PROVIDER` | `openai` or `anthropic` |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Provider credentials |
| `VISION_MOCK_MODE` | `true` runs the app fully offline with synthetic results — great for demos/CI |
| `DATABASE_URL` | SQLite (default) or PostgreSQL (`postgresql+asyncpg://...`) |
| `MAX_UPLOAD_SIZE_MB` | Upload size cap (default 15MB) |
| `ALLOWED_MIME_TYPES` | Allowed image types (default `image/jpeg,image/png`) |
| `USE_CELERY` | `false` = FastAPI BackgroundTasks; `true` = Celery + Redis |
| `CORS_ORIGINS` | Comma-separated allowed origins |
| `INTERNAL_API_KEY` | Optional shared-secret gate (wire into endpoints as needed) |
| `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS` | In-memory rate-limit scaffolding |
| `EMAIL_MOCK_MODE` | `true` (default) writes "sent" report emails to `REPORT_OUTPUT_DIR/mock_outbox/` instead of using real SMTP |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_USE_TLS` / `SMTP_FROM_ADDRESS` / `SMTP_FROM_NAME` | Real email delivery settings (only used when `EMAIL_MOCK_MODE=false`) |

## API reference

Base path: `/api/v1`

### `POST /inspections/upload`

Multipart form upload.

| Field | Required | Notes |
|---|---|---|
| `file` | yes | JPEG or PNG, ≤15MB |
| `inspector_name` | no | Free text |
| `inspector_email` | no | If provided, the completed report is automatically emailed here (see [Email delivery](#email-delivery--mobile-login)) |
| `site_location` | no | Free text |
| `notes` | no | Free text |

Response `202 Accepted`:
```json
{ "inspection_id": "b6b3...", "status": "PENDING", "message": "Upload received. Analysis in progress." }
```

### `GET /inspections/{inspection_id}`

Poll for status and results.

```json
{
  "id": "b6b3...",
  "status": "COMPLETED",
  "asset": {
    "asset_type": "Pressure Gauge",
    "manufacturer": "Ashcroft",
    "model_number": "1279",
    "serial_or_tag_number": "PG-1042",
    "confidence_score": 0.92
  },
  "defects": [
    {
      "defect_type": "Corrosion",
      "severity": "Medium",
      "location_description": "Base fitting threads",
      "recommendation": "Clean and inspect; re-check next cycle."
    }
  ],
  "overall_condition": "ACCEPTABLE",
  "overall_summary": "...",
  "is_compliant": true,
  "safety_hazards_detected": [],
  "immediate_action_required": false,
  "inspector_email": "inspector@example.com",
  "email_status": "SENT",
  "image_url": "/api/v1/inspections/b6b3.../image"
}
```

### `GET /inspections/{inspection_id}/report`

Returns a self-contained, printable HTML report (`text/html`). Returns `409 Conflict` if the inspection hasn't completed yet.

### `GET /inspections/{inspection_id}/image`

Streams the original uploaded photo (never the raw filesystem path — served through a validated route).

### `GET /inspections?limit=50`

Lists recent inspections (for the dashboard's "Recent Inspections" panel).

All errors use a standardized envelope:
```json
{ "error": "validation_error", "detail": "...", "status_code": 422, "path": "/api/v1/inspections/upload" }
```

## Running the demo pipeline

Runs the full flow end-to-end: seed 3 real sample photos → start the server → simulate 3 inspector uploads → wait for AI analysis → print structured JSON → save HTML reports.

```bash
python scripts/run_demo.py
```

Reports land in `output_reports/inspection_<id>.html`. Pass `--no-server` if you already have `uvicorn` running separately, or `--port` to change the port.

To only (re-)fetch the sample images:

```bash
python scripts/fetch_test_images.py
```

(If offline, this automatically generates simple placeholder images instead of failing.)

## Running tests

```bash
pytest -v
```

The test suite runs entirely against `VISION_MOCK_MODE=true` and an isolated temp SQLite DB/uploads dir (see `tests/conftest.py`) — no external API calls, no shared state with your dev database.

Covers: upload validation (MIME sniffing, size limits, path-traversal safety), the full async lifecycle (upload → poll → completed → report), vision schema validation, and storage-service sanitization helpers.

## Security notes

- **MIME validation by content, not header:** uploads are sniffed via `libmagic`/Pillow, not the client-supplied `Content-Type`.
- **Safe filenames:** every stored file gets a server-generated UUIDv4 name; the client's original filename is stored only as metadata, never used on disk — eliminates path traversal.
- **Size limits:** enforced while streaming the upload, not after buffering the whole body.
- **Image integrity check:** Pillow fully decodes the image before it's accepted, rejecting polyglot/corrupt files.
- **CORS:** explicit allow-list via `CORS_ORIGINS`.
- **Rate limiting scaffolding:** simple in-memory sliding-window limiter (swap for Redis-backed in multi-worker production).
- **Global error handling:** all unhandled exceptions, validation errors, and vision-API timeouts return a standardized JSON error envelope — no stack traces leak to clients.
- **Structured-output validation:** every vision-model response is validated against a strict Pydantic schema before being trusted/persisted; invalid responses are retried, then surfaced as a `FAILED` inspection rather than silently stored.

## Project structure

```
├── app/
│   ├── main.py                   # FastAPI init, CORS, global error handlers
│   ├── config.py                 # Pydantic BaseSettings (.env loading)
│   ├── database.py                # SQLAlchemy async session manager & engine
│   ├── models/                    # Inspection, Asset, Defect ORM models
│   ├── schemas/                   # API schemas + strict vision JSON schema
│   ├── services/
│   │   ├── vision_engine.py       # Vision API call, structured parsing, retries
│   │   ├── storage_service.py     # Upload validation & safe file handling
│   │   ├── report_service.py      # HTML report compiler
│   │   ├── email_service.py       # Report email delivery (mock outbox / real SMTP)
│   │   ├── inspection_pipeline.py # Shared processing logic (BG task / Celery)
│   │   └── celery_app.py          # Optional Celery app
│   └── api/v1/
│       ├── endpoints/inspections.py
│       └── router.py
├── frontend/
│   ├── index.html                 # Inspection Studio dashboard
│   ├── report_view.html           # Standalone report viewer
│   └── app.js
├── android/                       # Native Kotlin/Compose mobile app (see below)
├── tests/                         # Pytest suite
├── test_assets/                   # Sample industrial images (seeded)
├── scripts/
│   ├── fetch_test_images.py
│   └── run_demo.py
├── .env.example
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Email delivery & mobile login

Both the web dashboard and the Android app let an inspector give an email address at upload time; once analysis completes, the report is emailed there automatically (`app/services/email_service.py`, wired into `app/services/inspection_pipeline.py`).

- **`EMAIL_MOCK_MODE=true` (default):** no real SMTP connection is ever made. Each "sent" email is written as an `.html` file to `output_reports/mock_outbox/`, so the whole login → capture → "email me the report" flow works completely offline — exactly like `VISION_MOCK_MODE` for the vision AI.
- **`EMAIL_MOCK_MODE=false`:** set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_ADDRESS` (and `SMTP_USE_TLS` as needed) in `.env`. For Gmail: `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, and an [App Password](https://myaccount.google.com/apppasswords) (not your normal password) for `SMTP_PASSWORD`.
- A failed or misconfigured email send never fails the inspection itself — it's tracked independently via `email_status` (`NOT_REQUESTED` / `PENDING` / `SENT` / `FAILED`) and `email_error_message` on the inspection record.
- "Login" (web or mobile) is intentionally simple: a name + email, stored client-side, with no password and no server-side session — it exists purely to label inspections and address the report email, not to gate access. There's no separate auth endpoint to configure.

## Android app

`android/` is a complete, real native Kotlin + Jetpack Compose Android Studio project — not a stub. It talks to this same backend over the REST API above.

**Screens:** Login (name + email, persisted locally via DataStore) → Capture (take a photo with the phone's camera, optional site/notes, upload) → Result (polls `GET /inspections/{id}` and renders the same condition badge / OCR specs / defects / compliance panel as the web dashboard) → History (recent inspections) → Settings (backend server URL).

**Why you build it, not this session:** producing an installable `.apk` requires the Android SDK and Gradle/Maven downloads from Google's and Gradle's servers — this cloud sandbox's network is allow-listed and those domains aren't reachable from here, so the APK can't be compiled in this environment. The full, real Kotlin source is included; you build it in Android Studio on your own machine, which has normal internet access.

### Building it

1. Install [Android Studio](https://developer.android.com/studio) if you don't have it.
2. Open the `android/` folder as a project (`File → Open`).
3. Let Gradle sync — Android Studio will fetch dependencies automatically the first time (this needs internet access on your machine, not this sandbox). The project intentionally omits the `gradlew` wrapper script/jar, since generating those also requires reaching Gradle's servers; Android Studio's bundled Gradle handles this transparently when you open the project (it may prompt to create the wrapper — accept it, or just let it sync with the bundled Gradle).
4. Run on a device or emulator: the green ▶ Run button, or `Build → Build Bundle(s) / APK(s) → Build APK(s)` for a standalone `.apk` to install manually (`Build → Build APK(s)`, then `Locate` the file under `app/build/outputs/apk/debug/`).
5. **Set the backend URL** in the app's Settings screen before uploading:
   - Emulator: the default `http://10.0.2.2:8000` already points at your Mac's `localhost:8000` — no change needed.
   - Real phone: find your Mac's LAN IP (`System Settings → Wi-Fi → Details…`, or `ipconfig getifaddr en0` in Terminal) and enter e.g. `http://192.168.1.42:8000`. Your phone and Mac must be on the same Wi-Fi network, and `uvicorn` must be started with `--host 0.0.0.0` (not just `127.0.0.1`) so it accepts connections from other devices:
     ```bash
     uvicorn app.main:app --host 0.0.0.0 --port 8000
     ```
   - The app allows plain HTTP (`usesCleartextTraffic`) since this is a local dev backend, not a public HTTPS API.

## Notes on the AI

- With `VISION_MOCK_MODE=true` (the default), no external API is called — a deterministic synthetic result is generated so you can exercise the entire product without any cost or API key.
- To use a real model, set `VISION_MOCK_MODE=false`, choose `VISION_PROVIDER=openai` or `anthropic`, and provide the matching API key.
- Reports are AI-assisted and are explicitly labeled as such; they are intended to accelerate — not replace — sign-off by a qualified human inspector.
