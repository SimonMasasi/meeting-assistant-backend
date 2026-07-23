# Meeting Assistant Backend

A FastAPI-based backend for managing meetings, audio recordings with speaker diarization, file uploads, and user authentication.

---

## Table of Contents

- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Project Structure](#project-structure)
- [Environment Variables](#environment-variables)
- [Installation](#installation)
- [Running the Application](#running-the-application)
- [Database Migrations](#database-migrations)
- [Running Tests](#running-tests)
- [Docker](#docker)
- [File Storage](#file-storage)
- [API Reference](#api-reference)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI 0.136+ |
| ORM | SQLModel (SQLAlchemy + Pydantic) |
| Database | PostgreSQL (psycopg2) |
| Migrations | Alembic (auto-applied on startup) |
| Auth | JWT — 5-min access, 7-day refresh tokens |
| Password hashing | bcrypt |
| Speaker diarization | pyannote-audio + PyTorch |
| File storage | Local filesystem or S3-compatible (Rustf) |
| MIME detection | python-magic |
| Package manager | [uv](https://docs.astral.sh/uv/) |

---

## Prerequisites

- Python 3.14+
- PostgreSQL
- [uv](https://docs.astral.sh/uv/) — `pip install uv`
- `libmagic` system library
  - macOS: `brew install libmagic`
  - Debian/Ubuntu: `apt-get install libmagic1`
- (Optional) Docker & Docker Compose for containerised deployment

---

## Project Structure

```
.
├── app.py                  # Application entry point
├── config.py               # Pydantic settings (loaded from .env)
├── alembic.ini             # Alembic configuration
├── alembic/
│   └── versions/           # Migration scripts
├── src/
│   ├── modules/
│   │   ├── auth/           # Registration, login, JWT, user profile
│   │   ├── meetings/       # Meetings CRUD and recording management
│   │   ├── settings/       # SMTP / email configuration
│   │   └── uploads/        # File upload and download
│   ├── shared/             # Database engine, base model, dependencies, routes
│   ├── tests/              # Integration and unit tests
│   └── utils/
│       ├── jwt_auth.py
│       ├── passwords.py
│       ├── generators.py
│       └── audio/          # Speaker diarization pipeline
├── docker/
│   └── docker-compose-rustf.yml   # Optional S3-compatible object store
├── Dockerfile
└── uploads_media/          # Local file storage (images, documents, others)
```

---

## Environment Variables

Copy the template below into a `.env` file at the project root and fill in your values.

```dotenv
# ── Application ──────────────────────────────────────────
DATABASE_URL=postgresql://user:password@localhost:5432/meeting_assistant
SECRET_KEY=your-secret-key-here          # long, random string
DEBUG=True
APP_HOST=0.0.0.0
APP_PORT=8000

# ── JWT ──────────────────────────────────────────────────
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_SECONDS=300        # 5 minutes
JWT_REFRESH_TOKEN_EXPIRE_SECONDS=604800    # 7 days
JWT_PASSWORD_RESET_TOKEN_EXPIRE_SECONDS=86400   # 24 hours

# ── File Storage (local by default) ──────────────────────
USE_RUSTF_UPLOADS=False

# ── Uploads ──────────────────────────────────────────────
# Cap for the single-request endpoint (POST /uploads/upload-file), which
# buffers the whole body in memory. Larger files must use resumable uploads.
MAX_UPLOAD_SIZE_BYTES=52428800          # 50 MB
# Cap for resumable (tus) uploads — meeting audio can reach 2 GB.
TUS_MAX_UPLOAD_SIZE_BYTES=2147483648    # 2 GB
TUS_UPLOAD_DIR=uploads_media/.tus       # scratch space for in-progress chunks
TUS_UPLOAD_EXPIRY_SECONDS=86400         # abandoned uploads reaped after 24 h

# ── Rustf / S3-compatible storage (optional) ─────────────
# USE_RUSTF_UPLOADS=True
# RUSTF_URL=http://localhost:9000
# RUSTF_ACCESS_KEY=admin
# RUSTF_SECRET_KEY=rustfadmin
# RUSTF_BUCKET_NAME=meeting-assistant
# RUSTF_REGION=us-east-1

# ── Speaker Diarization ───────────────────────────────────
PYNOTE_MODEL=pyannote/speaker-diarization-community-1
HUGGINGFACE_TOKEN=hf_your_token_here      # required for diarization
```

> `HUGGINGFACE_TOKEN` is only required if you use the speaker diarization feature (`/meetings/add_meeting_recording`).

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/SimonMasasi/meeting-assistant-backend.git
cd meeting-assistant-backend

# 2. Install dependencies (creates .venv automatically)
uv sync

# 3. Activate the virtual environment
source .venv/bin/activate   # macOS / Linux
# .venv\Scripts\activate    # Windows

# 4. Create your .env file and fill in the values
cp .env.example .env
```

---

## Running the Application

Migrations are applied automatically on startup.

```bash
uv run python app.py
```

The API will be available at `http://localhost:8000`.  
Interactive API docs (Scalar UI) are served at `http://localhost:8000/docs`.

---

## Database Migrations

Alembic is used for schema migrations. Migrations are applied automatically every time the application starts, so manual runs are only needed during development.

### Apply all pending migrations

```bash
uv run alembic upgrade head
```

### Create a new migration

```bash
uv run alembic revision --autogenerate -m "your migration description"
```

### Rollback one migration

```bash
uv run alembic downgrade -1
```

### View migration history

```bash
uv run alembic history --verbose
```

### Check current revision

```bash
uv run alembic current
```

---

## Running Tests

The test suite uses **pytest** with **SQLite** as an in-memory database, so no PostgreSQL instance is required. All environment variables are set automatically by `conftest.py`.

### Run all tests

```bash
uv run pytest
```

### Run with verbose output

```bash
uv run pytest -v
```

### Run a specific test file

```bash
uv run pytest src/tests/test_auth.py -v
```

### Run a specific test

```bash
uv run pytest src/tests/test_meetings.py::test_create_meeting -v
```

### Run only unit tests

```bash
uv run pytest src/tests/unit/ -v
```

### Run with coverage (requires pytest-cov)

```bash
uv add --dev pytest-cov
uv run pytest --cov=src --cov-report=term-missing
```

---

## Docker

### Build and run the application image

```bash
docker build -t meeting-assistant-backend .
docker run -p 8000:8000 --env-file .env meeting-assistant-backend
```

### Start the S3-compatible object store (Rustf)

If you want to use Rustf instead of local file storage, start it via Docker Compose:

```bash
docker compose -f docker/docker-compose-rustf.yml up -d
```

This exposes:
- `http://localhost:9000` — S3 API endpoint
- `http://localhost:9001` — Web console (admin UI)

Then update your `.env`:

```dotenv
USE_RUSTF_UPLOADS=True
RUSTF_URL=http://localhost:9000
RUSTF_ACCESS_KEY=admin
RUSTF_SECRET_KEY=rustfadmin
RUSTF_BUCKET_NAME=meeting-assistant
RUSTF_REGION=us-east-1
```

---

## File Storage

Two storage backends are supported and switched via the `USE_RUSTF_UPLOADS` environment variable.

| Mode | Config | Storage path |
|---|---|---|
| Local (default) | `USE_RUSTF_UPLOADS=False` | `uploads_media/` directory |
| Rustf / S3 | `USE_RUSTF_UPLOADS=True` | S3-compatible bucket |

Files are deduplicated by SHA-256 hash — uploading the same file twice returns the existing record.

### Upload paths

| Endpoint | Limit | Use for |
|---|---|---|
| `POST /uploads/upload-file` | `MAX_UPLOAD_SIZE_BYTES` (50 MB) | Small files, one request |
| `POST /uploads/tus` | `TUS_MAX_UPLOAD_SIZE_BYTES` (2 GB) | Meeting audio; resumable |

### Resumable uploads (tus)

Large recordings go over the [tus 1.0.0](https://tus.io/protocols/resumable-upload) protocol, which
splits the file into chunks and resumes from the server's offset after a dropped connection — a 2 GB
upload no longer restarts from zero. Supported extensions: `creation`, `termination`, `expiration`.

| Method | Path | Purpose |
|---|---|---|
| `OPTIONS` | `/uploads/tus` | Discover version, max size, extensions |
| `POST` | `/uploads/tus` | Create an upload (`Upload-Length` + `Upload-Metadata` required) → `Location` |
| `HEAD` | `/uploads/tus/{key}` | Current `Upload-Offset` — call this to resume |
| `PATCH` | `/uploads/tus/{key}` | Append a chunk at `Upload-Offset` |
| `DELETE` | `/uploads/tus/{key}` | Abandon the upload |

All except `OPTIONS` require the usual `Authorization: Bearer <token>`; an upload may only be resumed
by the user who created it. The final `PATCH` responds `200` with the standard `SingleResponse`
envelope containing the created file record, so no extra call is needed to get the file id.

Any tus client works, e.g. [`tus-js-client`](https://github.com/tus/tus-js-client):

```js
new tus.Upload(file, {
  endpoint: "http://localhost:8000/uploads/tus",
  headers: { Authorization: `Bearer ${token}` },
  chunkSize: 8 * 1024 * 1024,
  metadata: { filename: file.name, filetype: file.type },
})
```

**Operational notes**

- In-progress chunks are buffered under `TUS_UPLOAD_DIR`, so that volume needs roughly
  `TUS_MAX_UPLOAD_SIZE_BYTES` free per concurrent upload. Expired buffers are reaped at startup.
- Behind a reverse proxy, the body limit (nginx `client_max_body_size`) must exceed the client's
  **chunk** size, not the total file size — tus splits the upload.
- Uploads and transcription both stream to and from disk, so server memory stays flat regardless of
  file size.
