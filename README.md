# ResQNet — Animal Emergency Response & Rescue Accountability

**REPORT. PRIORITIZE. ASSIGN. RESCUE. VERIFY.**

ResQNet is an AI-assisted animal emergency coordination application for citizens, responders, NGO coordinators and administrators. It combines incident intake, human-reviewed triage, responder matching, assignment offers, rescue progress, evidence records and independent verification.

> This repository is a hackathon/demo application. It is not connected to a live emergency dispatch network. Use synthetic data for demonstrations and do not rely on it as the sole channel for a real animal emergency.

## What is implemented

- FastAPI backend with SQLAlchemy models, JWT authentication, role checks and SQLite/PostgreSQL-compatible configuration.
- React 19, TypeScript and Vite frontend with role-aware workspaces.
- Citizen registration and reporting; incident timeline and duplicate-candidate information.
- Deterministic natural-language extraction and optional Gemini extraction with deterministic fallback.
- Optional audio upload, Whisper transcription (requires `WHISPER_API_KEY`) and reporter-reviewed transcript insertion into the case description.
- Emergency triage, geographic responder eligibility/ranking, assignment offers, acceptance/decline and deadline expiry/escalation.
- Rescue progress updates, evidence records, SHA-256 hashes, authorized evidence listing/download with integrity checking, and coordinator/admin verification/closure endpoints.
- NGO handoff request/accept/decline backend and coordinator UI; ownership transfers only after acceptance, with handoff notifications.
- Leaflet/OpenStreetMap incident map using role-filtered case coordinates (Leaflet is loaded from a CDN).
- Optional Gemini vision animal-category classification with explicit manual fallback and user confirmation.
- Admin UI for account creation/activation, responder verification, organization creation and organization verification.
- Persistent assignment, handoff and verification notifications; analytics endpoints and a documented weighted responder reliability indicator.
- Alembic migrations and synthetic Salem demo seed scripts.

## Remaining limitations — do not present these as completed

- Gemini image classification is optional and requires `GEMINI_API_KEY`; live provider success was not tested in this environment. The result is advisory and must be confirmed by the reporter.
- Whisper transcription requires `WHISPER_API_KEY`; live transcription was not tested. Manual voice transcript editing/confirmation remains available when a transcript is returned.
- The interactive Leaflet map loads Leaflet and OpenStreetMap tiles from public external services; an internet connection is required. Cases without coordinates cannot be mapped.
- The reliability score is an operational indicator based on offer acceptance, completion, verification and expiry. It is not a validated measure of responder quality and should not be used as the sole basis for dispatch decisions.
- Background deadline processing runs in-process. Production startup refuses multiple workers while this design remains; use one API worker or migrate to a coordinated external job runner.
- Frontend dependency installation and the Vite production build could not be completed in the audit environment. Browser end-to-end tests and the full Salem UI scenario remain unverified.
- This is still a hackathon/demo application, not a production emergency dispatch service. Rate limiting, malware scanning, external security review, durable object storage, operational monitoring, backup and privacy/retention controls remain deployment work.

## Architecture and folder layout

```text
backend/       FastAPI app, SQLAlchemy models, services, migrations and pytest suite
frontend/      React + TypeScript + Vite application
scripts/       Synthetic Salem demo seed scripts
 docs/         Architecture, data model, API contract and workflow notes
start-backend.ps1
start-frontend.ps1
```

## Prerequisites

- Windows 11 and PowerShell 5.1+ (or PowerShell 7)
- Python 3.11 recommended
- Node.js 20.19+ or 22.12+ recommended for current Vite
- npm (lockfile included)

No Docker, GPU, paid API or PostgreSQL server is required for a local SQLite demo.

## Windows setup

Extract the ZIP to a writable folder. Open PowerShell in the extracted `ResQNet-Final` directory.

### 1. Backend

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\start-backend.ps1
```

The script creates `backend\.venv`, installs `backend\requirements.txt`, creates `backend\.env` from the example if missing, runs Alembic migrations and starts Uvicorn at `http://localhost:8000`.

For manual setup:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 2. Frontend

Open a second PowerShell window in the extracted project directory:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\start-frontend.ps1
```

The script installs dependencies with `npm ci` if needed and starts Vite at `http://localhost:5173`.

The frontend API base URL is configured in `frontend/.env` as `VITE_API_URL=http://localhost:8000/api/v1`.

### 3. API docs

Open `http://localhost:8000/docs` after the backend starts.

## Environment variables

The backend reads `backend/.env` (see `backend/.env.example`):

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Defaults to local SQLite (`sqlite:///./resqnet.db`) |
| `SECRET_KEY` | Replace with a long random secret before deployment |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT lifetime |
| `CORS_ORIGINS` | Comma-separated frontend origins |
| `SEED_DEMO_DATA` | Seeds a small default demo account set on an empty database |
| `GEMINI_API_KEY` | Optional Gemini text extraction and image classification |
| `WHISPER_API_KEY` | Optional OpenAI Whisper transcription provider key |
| `UPLOAD_DIR` | Local upload storage directory |

Do not commit `.env` files or production secrets. Local filesystem uploads require persistent storage and appropriate access controls in deployment.

## Salem synthetic demonstration

From the repository root, run the full demo seed using the backend virtual environment:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\seed_full_demo.py
```

The script loads `backend\.env`, targets the same database as the API, and creates or updates synthetic users, two Salem NGOs, responder profiles and sample cases. The automatic API seed also creates or repairs the five Demo Access accounts. The shared demo password is:

`ResQNetDemo!2026`

| Role | Email |
|---|---|
| Citizen | `citizen@resqnet.demo` |
| Second citizen | `citizen2@resqnet.demo` |
| Responder | `rescuer@resqnet.demo` |
| Second responder | `rescuer2@resqnet.demo` |
| NGO demo (coordinator workspace) | `ngo@resqnet.demo` |
| NGO coordinator | `coordinator@resqnet.demo` |
| Second NGO coordinator | `coordinator2@resqnet.demo` |
| Administrator | `admin@resqnet.demo` |

These are public synthetic credentials, not secure accounts. Never deploy with these credentials. The NGO demo is a separate account using the existing coordinator role and NGO operations workspace.

## Tests and verification

Run from `backend` with the virtual environment active:

```powershell
python -m pytest tests/ -v
```

The latest verification record is in [`COMPLETION_REPORT.md`](COMPLETION_REPORT.md). It distinguishes tests executed from features not yet implemented or not verified. A passing backend suite does not establish that every browser workflow or the frontend production build works.

## Deployment notes

1. Set `ENVIRONMENT=production` and a unique `SECRET_KEY` generated with `python -c "import secrets; print(secrets.token_hex(32))"`.
2. Use PostgreSQL for multi-user production deployment and test the migration path against the target database.
3. Configure restrictive `CORS_ORIGINS` and HTTPS at the reverse proxy.
4. Store uploads on durable private storage; do not expose the upload directory as a public static folder.
5. Disable demo seeding and remove all demo accounts before production.
6. Run a single API worker while the in-process deadline worker is enabled, or move deadline processing to a properly coordinated external job system.
7. Add monitoring, backups, retention policy, abuse controls and operational runbooks before any real-world use.

## Security and safety limitations

The application uses hashed passwords, expiring JWTs and role-based endpoint dependencies. Evidence file uploads now check MIME type, size and basic file signatures. This is not a complete security audit: production deployment still requires threat modelling, rate limiting, secret management, secure storage, malware scanning, privacy review and independent penetration testing. AI extraction is advisory only; human review remains necessary for emergency decisions and case closure.
