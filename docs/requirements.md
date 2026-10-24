# Requirements Specification: A2A Invoice Agent

Authoritative requirements extracted directly from `docs/assignment-specification.md`.

---

## 1. Overview & Evaluation Constraints
- **Goal**: Public HTTPS A2A Invoice Agent conforming to A2A HTTP+JSON 1.0. Decides actions for invoice packages, generates action proposals with bracketed evidence citations, safely validates continuation results from grader, executes only accepted actions, and produces receipts.
- **Grader Checks Limit**: Maximum 10 checks per 24 hours. Every "Check" or "Save" uses one check. The grader page reserves the last check for "Save". Saving with no checks left scores 0 marks. **Do not use grader checks during local development.**
- **Evaluation Scope**: 5 core tasks × 12 packages (60 packages total) + 1 hidden audit task per Check/Save.
- **Latency & Size Budget**:
  - Request timeout: 45 seconds per request; 160 seconds total verification.
  - Maximum response size: ≤ 512 KiB.

---

## 2. API Contract & Protocol Routes

### 2.1 Route Envelopes
- Discovery:
  - `GET /.well-known/agent-card.json` (Origin-level discovery, public, no auth)
- Relative to Base URL (`{base}`):
  - `POST {base}/message:send` -> Returns `{"task": Task}`
  - `GET  {base}/tasks/{id}` -> Returns `Task`
  - `GET  {base}/tasks` -> Returns `{"tasks": [Task, ...]}`
  - `POST {base}/tasks/{id}:cancel` -> Returns `Task`

### 2.2 Headers & Content Negotiation
- **`A2A-Version: 1.0`**: Required on all applicable A2A endpoints. Missing/different version returns HTTP 400.
- **`Content-Type: application/a2a+json`**: Required on POST requests (`/message:send`, `/tasks/{id}:cancel`).
- **Response Media Type**: Successful responses must return `application/a2a+json` (or `application/json`).
- **Authentication**:
  - `GET /.well-known/agent-card.json` is public.
  - All other routes require an exact `Authorization: Bearer <token>`.
  - Missing or invalid auth returns HTTP 401 / 403.
  - Each distinct Bearer token is treated as an isolated principal.

### 2.3 ProtoJSON Enums & Formats
- Roles: `"ROLE_USER"`, `"ROLE_AGENT"`
- Task States:
  - `"TASK_STATE_INPUT_REQUIRED"` (initial state waiting for grader continuation)
  - `"TASK_STATE_COMPLETED"` (after valid result continuation is processed)
  - `"TASK_STATE_CANCELED"` (after successful cancellation)
  - (Internal states `"TASK_STATE_SUBMITTED"` and `"TASK_STATE_WORKING"` may be used transiently)

---

## 3. Agent Card Specification (`GET /.well-known/agent-card.json`)
The response must contain:
- `name`: Non-empty string
- `description`: Non-empty string
- `version`: Non-empty string
- `capabilities`: Object-valued capabilities
- `skills`: Array containing an `invoice_action_agent` skill with non-empty `name`, `description`, and `tags`
- `supportedInterfaces`: Array containing an interface with:
  - URL matching the exact base URL
  - `protocolBinding`: `"HTTP+JSON"`
  - `protocolVersion`: `"1.0"`
- `defaultInputModes`: Array including `"application/vnd.ga5.invoice-claim-batch+json"`
- `defaultOutputModes`: Array including:
  - `"application/vnd.ga5.invoice-action-proposals+json"`
  - `"application/vnd.ga5.invoice-action-receipts+json"`

---

## 4. Message Flow & Task Lifecycle

### 4.1 Initial Message (`POST /message:send`)
Incoming payload:
```json
{
  "message": {
    "messageId": "...",
    "role": "ROLE_USER",
    "parts": [{
      "mediaType": "application/vnd.ga5.invoice-claim-batch+json",
      "data": {
        "batchId": "...",
        "policyRevision": "...",
        "packages": [...]
      }
    }]
  },
  "configuration": {
    "returnImmediately": false,
    "historyLength": 20,
    "acceptedOutputModes": [
      "application/vnd.ga5.invoice-action-proposals+json",
      "application/vnd.ga5.invoice-action-receipts+json"
    ]
  }
}
```

### 4.2 Proposals Artifact (`application/vnd.ga5.invoice-action-proposals+json`)
The agent responds with a `Task` in `"TASK_STATE_INPUT_REQUIRED"`.
- Must contain initial message in `Task.history`.
- Contains exactly **one** artifact Part with mediaType `application/vnd.ga5.invoice-action-proposals+json`.
- **Must NOT** include a receipt artifact at this stage.
- Data schema:
```json
{
  "batchId": "...",
  "proposals": [{
    "packageId": "...",
    "actionId": "durable unique id (at least 12 characters)",
    "action": "settle_invoice | request_approval | hold_invoice | reject_duplicate | open_exception",
    "facts": {
      "vendorName": "...",
      "invoiceNumber": "...",
      "amountMinor": 12345,
      "currency": "INR"
    },
    "evidenceRefs": ["exact decisive references from the documents"],
    "rationale": "60–1500 characters; name the action and cite at least two evidence refs"
  }]
}
```
Rules:
- Actions must be one of:
  1. `settle_invoice`: valid, reconciled, within autonomous authority.
  2. `request_approval`: commercially valid, outside delegated authority.
  3. `hold_invoice`: payment pauses until stated verification completes.
  4. `reject_duplicate`: same commercial invoice was already paid.
  5. `open_exception`: material records conflict and need exception workflow.
- `packageId` and `actionId` must be unique in the batch.
- `evidenceRefs`: exactly three decisive bracketed references from the paragraph determining the action. Exclude cover sheets, archive examples, and decoys.
- `rationale`: 60–1500 characters, naming the action and citing at least two evidence refs.

### 4.3 Continuation & Results Processing
Grader sends continuation:
```json
{
  "message": {
    "messageId": "new id",
    "taskId": "exact task id",
    "contextId": "exact context id",
    "role": "ROLE_USER",
    "parts": [{
      "mediaType": "application/vnd.ga5.invoice-action-results+json",
      "data": {
        "batchId": "...",
        "results": [{
          "packageId": "...",
          "actionId": "...",
          "action": "...",
          "outcome": "ACCEPTED | REJECTED",
          "receiptNonce": "unpredictable..."
        }]
      }
    }]
  }
}
```
Validation rules:
- Reject continuation if `principal`, `taskId`, `contextId`, `batchId`, `packageId`, `actionId`, or `action` do not match stored task/proposals.
- If valid:
  - Task transitions to `"TASK_STATE_COMPLETED"`.
  - Message added to `Task.history`.
  - Retain the proposal artifact.
  - Add exactly **one** artifact Part with mediaType `application/vnd.ga5.invoice-action-receipts+json`.
  - Schema:
```json
{
  "batchId": "...",
  "executions": [{
    "packageId": "...",
    "actionId": "...",
    "action": "...",
    "receiptNonce": "...",
    "facts": {
      "vendorName": "...",
      "invoiceNumber": "...",
      "amountMinor": 12345,
      "currency": "INR"
    },
    "evidenceRefs": ["..."]
  }]
}
```
- `executions` contains **ACCEPTED results only**. Rejected proposals are never executed.

---

## 5. Persistence, Idempotency & Safety

### 5.1 Idempotency Key & Canonical Fingerprint
- Key: `(Bearer principal, messageId)`.
- Fingerprint: SHA-256 hash of recursively key-sorted compact JSON of `message` only (ignoring `configuration`).
- Same key + same fingerprint: Return existing `Task` without re-executing model or actions.
- Same key + different fingerprint: Return HTTP 409 with error `IDEMPOTENCY_CONFLICT`.

### 5.2 Terminal Tasks & Cancellation vs Continuation Race
- A non-terminal task can be canceled via `POST /tasks/{id}:cancel`, setting state to `"TASK_STATE_CANCELED"`.
- Once terminal (`COMPLETED` or `CANCELED`), no task fields may change.
- If receipt and cancel arrive concurrently:
  - Exactly one returns HTTP 200 and the other returns HTTP 409.
  - Final result must be either `COMPLETED` with all receipts, or `CANCELED` with zero receipts. Never both.

### 5.3 Principal Isolation
- Each Bearer token is an isolated tenant.
- Listing tasks (`GET /tasks`) returns only the authenticated principal's tasks.
- Requesting an outsider's task via ID returns 403 or 404 with generic error body.
- Never leak cross-user task IDs or existence.

### 5.4 Decision Caching
- Batch 12 packages in one model call.
- Cache decisions by canonical package content (sorted JSON hash of package text/data).
- When identical package data is processed under new batch/message/task IDs, reuse cached decision with zero LLM latency.

---

## 6. Implementation Architecture

1. `app/config.py`: Environment configuration (Host, Port, Base URL, Database URL, LLM API Keys, etc.).
2. `app/database.py`: SQLAlchemy engine, session maker, base model.
3. `app/models/`: Models for `Task`, `Message`, `Artifact`, `IdempotencyRecord`, `PackageDecisionCache`.
4. `app/schemas/`: Pydantic models for A2A messages, Task, Agent Card, Proposals, Results, Receipts.
5. `app/services/`:
   - `decision_engine.py`: Batch AI reasoning, fallback extractor, semantic caching.
   - `idempotency.py`: Canonical message fingerprinting & conflict detection.
   - `task_service.py`: Task state machine, proposal generation, continuation validation, receipt generation, cancellation.
6. `app/api/`:
   - `deps.py`: Auth header extractor (resolves principal), A2A-Version & Content-Type validators.
   - `agent_card.py`: `GET /.well-known/agent-card.json`.
   - `a2a.py`: `/message:send`, `/tasks/{id}`, `/tasks`, `/tasks/{id}:cancel`.
7. `tests/`: Pytest test suite testing all protocol envelopes, idempotency, auth, cancellation races, continuation validation, and isolation.
