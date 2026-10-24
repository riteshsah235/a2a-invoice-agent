# A2A Invoice Agent: Decide and Act Safely

Autonomous HTTPS invoice decision agent built with **FastAPI**, **SQLAlchemy**, **PostgreSQL**, **Pydantic**, and **pytest**, implementing the **A2A HTTP+JSON 1.0** protocol specification.

The agent analyzes 12-package invoice batches, selects evidence-based business actions (`settle_invoice`, `request_approval`, `hold_invoice`, `reject_duplicate`, `open_exception`), cites exact bracketed evidence references, safely returns proposals in `TASK_STATE_INPUT_REQUIRED`, validates continuation results strictly, and generates verifiable execution receipts upon approval.

---

## Architecture & Protocol Compliance

### 1. Endpoint Envelopes
- **Discovery**: `GET /.well-known/agent-card.json` (Public origin-level discovery).
- **Send Message**: `POST {base}/message:send` -> Returns `{"task": Task}`.
- **Get Task**: `GET {base}/tasks/{id}` -> Returns `Task`.
- **List Tasks**: `GET {base}/tasks` -> Returns `{"tasks": [Task, ...]}`.
- **Cancel Task**: `POST {base}/tasks/{id}:cancel` -> Returns `Task`.
- **Health Check**: `GET /healthz` -> Returns `{"status": "ok"}`.

### 2. Protocol & Security Guarantees
- **A2A-Version & Media Types**: Requires `A2A-Version: 1.0` and `application/a2a+json` on POST requests. All responses return `application/a2a+json` within the 512 KiB size limit.
- **Multi-Tenant Principal Isolation**: Every distinct Bearer token is treated as an isolated user. Outsiders cannot read or mutate other principals' tasks (generic 404 response without leaking task existence).
- **Idempotency & Replay**: Deduplicates by `(Bearer principal, messageId)` using a SHA-256 fingerprint of the recursively key-sorted compact JSON `message` object (ignoring configuration). Conflicting reuse returns HTTP 409 `IDEMPOTENCY_CONFLICT`.
- **Decision Caching**: Invoice packages are cached by their canonical content hash (`package_hash`). Personalized batches reuse cached semantic decisions instantly without redundant model calls.
- **Safe Continuation & Receipts**: Only proposals returned as `ACCEPTED` with an unpredictable `receiptNonce` are executed into `application/vnd.ga5.invoice-action-receipts+json`. Rejected proposals remain in history and are never executed.
- **Cancellation Safety**: Non-terminal tasks can be canceled. Terminal tasks (`COMPLETED` or `CANCELED`) are immutable. Simultaneous cancellation and continuation races are handled with transactional atomicity (one returns 200, the other returns 409).

---

## Project Structure

```text
a2a-invoice-agent/
├── .env.example              # Environment variables template
├── .gitignore                # Git ignore rules (prevents secret leaks)
├── alembic.ini               # Alembic configuration
├── alembic/                  # Database migration scripts
│   ├── env.py
│   └── versions/
│       └── f28456b0053d_initial_migration.py
├── app/
│   ├── __init__.py
│   ├── main.py               # FastAPI entrypoint, lifespan, middlewares
│   ├── config.py             # Pydantic BaseSettings configuration
│   ├── database.py           # SQLAlchemy engine & session factory
│   ├── models/               # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   └── entities.py       # Task, Idempotency, Proposals, Cache models
│   ├── schemas/              # Pydantic validation models
│   │   ├── __init__.py
│   │   ├── a2a.py            # Protocol message & Task schemas
│   │   ├── agent_card.py     # Agent Card schema
│   │   └── invoice.py        # Proposal & receipt data schemas
│   ├── services/             # Core business logic & state machine
│   │   ├── decision_engine.py# Evidence citation & canonical cache
│   │   └── task_service.py   # State machine, idempotency, lifecycle
│   ├── api/                  # HTTP route handlers
│   │   ├── deps.py           # Auth, headers, and principal derivation
│   │   ├── agent_card.py     # GET /.well-known/agent-card.json
│   │   ├── a2a.py            # A2A endpoints (/message:send, /tasks, etc.)
│   │   └── health.py         # GET /healthz
│   └── utils/
│       └── crypto.py         # Canonical JSON serialization & hashing
├── docs/
│   ├── assignment-specification.md
│   └── requirements.md
├── pytest.ini
├── render.yaml               # Render Blueprint configuration
├── requirements.txt
└── tests/
    ├── conftest.py           # In-memory test DB & fixtures
    ├── test_agent_card.py
    ├── test_concurrency.py   # Async multi-threaded concurrency race tests
    ├── test_idempotency_and_replay.py
    ├── test_invoices_and_lifecycle.py
    ├── test_isolation_and_cancellation.py
    └── test_protocol_and_auth.py
```

---

## Local Development & Setup

### 1. Setup Virtual Environment
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
```

### 3. Apply Database Migrations
```bash
alembic upgrade head
```

### 4. Run Automated Test Suite
```bash
pytest -v
```

### 5. Start Local Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
- Agent Card: `http://localhost:8000/.well-known/agent-card.json`
- Health check: `http://localhost:8000/healthz`
- A2A endpoints: `http://localhost:8000/a2a/message:send`

---

## Render Deployment & Cost Optimization Guide

### Deployment Architecture & Plans
- **Web Service (`a2a-invoice-agent`)**:
  - **Plan**: `free` ($0/month).
  - Lowest-cost configuration compliant with the assignment requirements.
  - Spins down after 15 minutes of inactivity; spins up automatically upon receiving HTTP requests.
  - Health check path configured at `/healthz`.
  - Binds to Render's dynamic `$PORT` environment variable.
- **PostgreSQL Database (`invoice-agent-db`)**:
  - **Plan in `render.yaml`**: `standard` (retained persistent plan; lowest persistent tier `basic-256mb` at ~$7/month can also be selected in Render Dashboard).
  - **Cost Implication**: Render's free PostgreSQL tier automatically expires and deletes all data after 30 days. To ensure reliable, persistent task state, idempotency replay records, and audit log integrity across evaluation cycles, ephemeral SQLite or expiring free PostgreSQL must not be used in production. A paid persistent PostgreSQL tier (starting at ~$7/month for `basic-256mb` up to standard) is required.

### Option A: Using Render Blueprint (`render.yaml`)
1. Push this repository to GitHub.
2. In the Render Dashboard, click **New +** -> **Blueprint**.
3. Connect your repository. Render parses `render.yaml` to provision:
   - Persistent PostgreSQL database (`invoice-agent-db`).
   - Python Web Service (`a2a-invoice-agent`, `free` plan) with build command `pip install -r requirements.txt && alembic upgrade head` and health check at `/healthz`.
4. In the Web Service Environment settings on Render:
   - `BASE_URL` is configured automatically via `render.yaml` as `https://a2a-invoice-agent-kkbk.onrender.com/a2a/`. (Verify in Render Dashboard under Environment).
   - (Optional) Set `GEMINI_API_KEY` or `OPENAI_API_KEY` if using external LLM APIs. Never commit secret keys to Git.

### Option B: Manual Service Creation
1. Create a **PostgreSQL** database on Render (select a persistent tier such as `basic-256mb` or `standard`).
2. Create a **Web Service** on Render:
   - Environment: `Python 3`
   - Plan: `Free`
   - Build Command: `pip install -r requirements.txt && alembic upgrade head`
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Health Check Path: `/healthz`
   - Add environment variables:
     - `DATABASE_URL`: Your Render PostgreSQL Internal Connection String.
     - `BASE_URL`: `https://a2a-invoice-agent-kkbk.onrender.com/a2a/`

---

## Pre-Submission Verification Checklist

Before running any grader Check or Save, verify all items:
- [x] **Agent Card Discovery**: `GET /.well-known/agent-card.json` returns valid JSON with skills, interfaces, and media types without authentication.
- [x] **Bearer Authentication**: Non-Bearer or missing token returns 401.
- [x] **Protocol Headers**: `A2A-Version: 1.0` enforced; invalid versions return 400.
- [x] **Content-Type**: `application/a2a+json` enforced on POST requests.
- [x] **Payload Limits**: Payloads over 512 KiB return 413.
- [x] **Task Lifecycle**: Initial claim batch returns `TASK_STATE_INPUT_REQUIRED` with exactly 1 proposal artifact.
- [x] **Proposal Quality**: Unique package and action IDs; exactly 3 decisive bracketed references; 60–1500 char rationale citing evidence.
- [x] **Continuation & Receipts**: Continuation results strictly validated; receipt artifact produced only for accepted proposals; rejected proposals never executed.
- [x] **Canonical Idempotency**: Compact key-sorted message hashing prevents replay attacks; altered content returns 409 `IDEMPOTENCY_CONFLICT`.
- [x] **User Isolation**: Out-of-band principals receive empty list on `GET /tasks` and generic 404 on task-specific routes.
- [x] **Terminal Immutability**: Completed or cancelled tasks reject conflicting mutations with 409.
- [x] **Persistent Storage**: PostgreSQL integration configured with Alembic migrations.
