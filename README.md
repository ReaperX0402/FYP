# IPDS FYP Repository

A Flask-based **Image Proof/Inspection Data System (IPDS)** for guided image capture workflows with:

- Olympus TG-7 Wi-Fi ingestion
- Session/job/operator tracking in PostgreSQL
- Image decisioning (accept/reject)
- Advisory AI review manifest (angle + blur + duplicate checks)
- Export packaging (ZIP + manifest + metadata + watermark)
- Local archival and archive session management

---

## Table of Contents

1. [What this system does](#what-this-system-does)
2. [Core workflow](#core-workflow)
3. [Feature-by-feature functionality](#feature-by-feature-functionality)
4. [Architecture overview](#architecture-overview)
5. [Tech stack](#tech-stack)
6. [Repository structure](#repository-structure)
7. [Setup](#setup)
8. [Running the app](#running-the-app)
9. [Database initialization and migrations](#database-initialization-and-migrations)
10. [Configuration](#configuration)
11. [HTTP routes](#http-routes)
12. [Data folders and file lifecycle](#data-folders-and-file-lifecycle)
13. [AI model utilities and scripts](#ai-model-utilities-and-scripts)
14. [Troubleshooting](#troubleshooting)
15. [Notes / known caveats](#notes--known-caveats)

---

## What this system does

This project supports an inspection process where operators:

1. Log in with an Operator ID.
2. Create a job and start an import session for a UUT (unit under test).
3. Ingest photos from an Olympus TG-7 camera over Wi-Fi.
4. Review each photo and mark it **accepted** or **rejected**.
5. Use AI-generated advisory analysis during review (non-authoritative).
6. Export accepted media into a versioned ZIP package with a manifest.
7. Archive all session images locally and manage archived sessions.

The database is the source of truth. AI output is advisory only.

---

## Core workflow

### 1) Authentication
- Operator enters `operator_id` on `/login`.
- Session cookie stores operator context.

### 2) Job + Session
- Create a job (`/jobs/new`).
- Create an import session (`/sessions/new`) with `job_id` + `uut_serial`.

### 3) Ingestion
- Trigger ingest (`/sessions/<id>/ingest/run`).
- Adapter connects to Olympus TG-7 Wi-Fi API.
- JPEGs are listed, deduplicated, downloaded, integrity-checked, and inserted into DB.

### 4) Decisions
- Review media (`/sessions/<id>/decide`).
- Set single or bulk decisions (`accepted`/`rejected`) with optional reason/notes.

### 5) AI review artifact
- While opening decision page, the app builds `data/ai_review/session_<id>_ai_review.json`.
- It includes predicted object/angle, blur warning, duplicate warning, target mismatch warning, and missing-angle summary.

### 6) Export + archive
- Export accepted media (`/sessions/<id>/export/run`).
- Export pipeline renames files, embeds metadata, burns watermark/logo, builds `manifest.json`, creates ZIP.
- Same flow archives all media for the session in `data/archive/<uut>_<session_id>/`.

### 7) Close/cancel/amend/retake/rework session
- Session completion requires at least one successful archived export.
- Completed/failed sessions are visible on archive page.
- Completed sessions can be amended (re-opened), or used to create retake/rework sessions.

---

## Feature-by-feature functionality

## 1) Camera ingestion (Olympus TG-7)

- Adapter class: `OlympusTG7Adapter` (`src/adapter/olympus.py`)
- Connects through `olympuswifi.camera.OlympusCamera`.
- Lists media from `/DCIM` and filters JPEG/JPG only.
- Converts vendor metadata to internal `CameraMedia` records.
- Downloads binary data through camera API.

Integrity and dedupe controls:
- Uses `.part` temporary file write before final rename.
- Validates expected file size before finalizing.
- Supports SHA-256 hashing of written file.
- Deduplicates by `(adapter, vendor_id)` via DB unique constraint + idempotent insert logic.

## 2) Session and job management

Jobs:
- Create new jobs.
- View recent jobs.
- Close jobs (blocked when running sessions exist).

Import sessions:
- Create session with `job_id`, `uut_serial`, and current operator.
- Lifecycle states: `running`, `completed`, `failed`.
- Additional purpose states: `initial`, `retake`, `rework`, `other`.

Archive management:
- Completed and cancelled sessions are listed with media counts.
- Can amend completed sessions (set back to running).
- Can spawn retake/rework sessions from archived sessions.

## 3) Media decisioning

- Single media decision endpoint and bulk decision endpoint.
- Validation ensures media belongs to the selected session.
- Upsert behavior allows modifying prior decisions.
- Decision values strictly enforced as `accepted` or `rejected`.

## 4) AI advisory review manifest

`AIReviewManifestService` performs:
- Classification via YOLO model (`AngleClassifier`).
- Blur detection via variance-of-Laplacian (`BlurDetector`).
- Duplicate-angle warning detection.
- Target mismatch warning (image object differs from dominant session object).
- Missing required angle suggestion based on: `front`, `back`, `left`, `right`, `top`.

Output file:
- `data/ai_review/session_<import_session_id>_ai_review.json`

Important boundary:
- AI manifest does **not** alter DB decisions.
- It is generated for operator guidance and traceability only.

## 5) Export and archival

Export pipeline (`src/core/export_zip.py`):
- Gets accepted media for session.
- Builds versioned ZIP name: `<UUT_SERIAL>_<SESSION_ID>.zip`, with `_vN` fallback when needed.
- Renames photo files to:
  - `<UUT_SERIAL>_<OPERATOR_ID>_<UTC_TIMESTAMP>_<SEQ>.<ext>`
- Embeds metadata into image EXIF.
- Burns a visual watermark containing serial + datetime (+ logo when available).
- Generates manifest JSON with per-file SHA-256 + size + source reference + decision metadata.
- Stores sidecar manifest: `<zipname>.manifest.json`.
- Writes DB rows into:
  - `exports`
  - `local_archives`
- Copies all session media into archive folder and records verification status.

---

## Architecture overview

Layered structure:

- **Web layer**: Flask app + blueprints (`src/web/routes/*`)
- **Core services**: ingestion, decisions, export, AI manifest (`src/core/*`)
- **Data layer**: SQLAlchemy models + repositories (`src/db/*`)
- **Adapters**: camera interface + Olympus implementation (`src/adapter/*`)
- **Utilities**: hashing, EXIF metadata embed, watermark (`src/utils/*`)

---

## Tech stack

- Python 3.x
- Flask
- SQLAlchemy
- PostgreSQL (`psycopg[binary]`)
- Alembic
- YOLO/Ultralytics
- OpenCV
- Torch
- NumPy
- Pillow
- olympuswifi

Dependencies are listed in `requirements.txt`.

---

## Repository structure

```text
.
├── run.py                      # Flask entrypoint
├── requirements.txt
├── alembic.ini
├── alembic/
│   └── versions/
├── src/
│   ├── app.py                  # create_app(), blueprint registration
│   ├── config.py               # env-backed settings
│   ├── startup.py              # required directory creation
│   ├── adapter/
│   │   ├── base.py
│   │   └── olympus.py          # Olympus TG-7 Wi-Fi adapter
│   ├── web/
│   │   ├── auth.py             # login_required/session helper
│   │   ├── routes/
│   │   │   ├── auth.py
│   │   │   ├── ingestion.py
│   │   │   ├── decisions.py
│   │   │   ├── exports.py
│   │   │   └── sessions.py
│   │   └── templates/
│   ├── core/
│   │   ├── ingest.py
│   │   ├── ingestion_service.py
│   │   ├── decision_service.py
│   │   ├── ai_review_manifest.py
│   │   └── export_zip.py
│   ├── db/
│   │   ├── base.py
│   │   ├── models.py
│   │   ├── session.py
│   │   ├── repo_media.py
│   │   ├── repo_decisions.py
│   │   ├── init_db.py
│   │   └── schema.sql
│   ├── ai_model/
│   │   ├── angle_classifier.py
│   │   ├── angle_suggester.py
│   │   ├── blur_detector.py
│   │   └── *.pt                # trained model weights
│   ├── utils/
│   │   ├── hashing.py
│   │   ├── embed.py
│   │   └── watermark.py
│   └── assets/
│       ├── fonts/
│       └── images/
├── scripts/
│   ├── smoke_test_db.py
│   ├── test_angle_classifier.py
│   ├── test_angle_batch.py
│   └── test_blur_threshold.py
└── data/
    ├── incoming/
    ├── archive/
    ├── exports/
    ├── ai_review/
    └── test_*                  # sample image fixtures
```

---

## Setup

## 1) Create virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

## 2) Install dependencies

```bash
pip install -r requirements.txt
```

## 3) Create `.env`

Example:

```env
SECRET_KEY=change-me
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
FLASK_DEBUG=true

DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/ipds

DATA_ROOT=./data
INCOMING_DIR=./data/incoming
ARCHIVE_DIR=./data/archive
EXPORT_DIR=./data/exports
AI_REVIEW_DIR=./data/ai_review
```

## 4) Prepare PostgreSQL

- Create database.
- Ensure `DATABASE_URL` points to it.
- Initialize schema using one of the options below.

---

## Running the app

```bash
python run.py
```

Then open:

- `http://localhost:5000/login`

Note: login optionally validates operator existence from DB if the `operators` table is available.

---

## Database initialization and migrations

You can initialize DB with any of these approaches.

## Option A: SQL schema file

```bash
psql "$DATABASE_URL" -f src/db/schema.sql
```

## Option B: SQLAlchemy create_all helper

```python
from src.db.session import build_engine
from src.db.init_db import init_db

engine = build_engine()
init_db(engine)
```

## Option C: Alembic

```bash
alembic upgrade head
```

Alembic baseline migration exists at:
- `alembic/versions/fe94a4f469db_baseline_ipds.py`

---

## Configuration

Environment-backed settings in `src/config.py`:

- `SECRET_KEY`
- `FLASK_HOST`
- `FLASK_PORT`
- `FLASK_DEBUG`
- `DATABASE_URL` (consumed by DB session builder)
- `DATA_ROOT`
- `INCOMING_DIR`
- `ARCHIVE_DIR`
- `EXPORT_DIR`
- `AI_REVIEW_DIR`

---

## HTTP routes

## Auth
- `GET /login` - login page
- `POST /login` - set operator session
- `GET /logout` - clear session

## Dashboard / Sessions
- `GET /dashboard`
- `GET /sessions/new`
- `POST /sessions/new`
- `POST /sessions/<id>/complete`
- `POST /sessions/<id>/cancel`
- `GET /sessions/archive`
- `POST /sessions/<id>/amend`
- `POST /sessions/<id>/retake`
- `POST /sessions/<id>/rework`

## Ingestion / Jobs
- `GET /sessions/<id>/ingest`
- `POST /sessions/<id>/ingest/run`
- `GET /jobs/new`
- `POST /jobs/new`
- `GET /jobs`
- `POST /jobs/<job_id>/close`

## Decisions
- `GET /sessions/<id>/decide`
- `POST /sessions/<id>/decide/bulk`
- `POST /media/<media_id>/decide`
- `GET /media/<media_id>/file` (safe file serving from allowed roots)

## Exports
- `GET /sessions/<id>/export`
- `POST /sessions/<id>/export/run`

---

## Data folders and file lifecycle

## Incoming
- Path pattern: `data/incoming/session_<session_id>/...`
- Created during ingestion.
- Deleted when session is completed/cancelled via safe-guarded deletion.

## Archive
- Path pattern: `data/archive/<uut_serial>_<session_id>/...`
- Stores copied media and archive `manifest.json`.

## Exports
- ZIP path: `data/exports/<uut_serial>_<session_id>[ _vN].zip`
- Sidecar manifest path: `<zip>.manifest.json`

## AI review
- Path: `data/ai_review/session_<session_id>_ai_review.json`
- Regenerated on each decision-page load.

---

## AI model utilities and scripts

Useful scripts:

```bash
python scripts/smoke_test_db.py
python scripts/test_angle_classifier.py
python scripts/test_angle_batch.py
python scripts/test_blur_threshold.py
```

What they do:
- `smoke_test_db.py`: inserts sample operator/job/session/media/decisions/export/archive rows.
- `test_angle_classifier.py`: single-image classifier smoke test + angle suggestion.
- `test_angle_batch.py`: batch image prediction for a folder.
- `test_blur_threshold.py`: prints blur score and warning for sample images.

---

## Troubleshooting

## `DATABASE_URL is not set`
Set `.env` (or shell env) and restart app.

## Login rejects operator ID
Ensure row exists in `ipds.operators` table (or disable strict check in route logic).

## Ingestion fails to connect to camera
Common causes:
- host is not connected to TG-7 Wi-Fi SSID,
- camera not in Wi-Fi mode,
- camera sleeping,
- network mismatch.

## Export fails with "No accepted media found"
At least one media row in the session must be decided as `accepted`.

## Media preview 404 on decision page
File may have moved/been removed; app tries incoming path first, then archive candidates.

---

## Notes / known caveats

- AI review is advisory and explicitly non-authoritative.
- Some scripts reference model/image filenames; verify paths in your local environment.
- `src/main.py` is a direct adapter ingestion proof script; main web app entrypoint is `run.py`.
- Alembic includes a baseline migration and a later no-op migration stub.

---
