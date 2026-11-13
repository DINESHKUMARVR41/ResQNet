# ResQNet — Animal Emergency Response Platform

**Report. Prioritize. Assign. Rescue. Verify.**

ResQNet is an AI-assisted animal emergency response and rescue accountability platform connecting citizens, animal rescuers, NGOs, and coordinators.

## Quick Start (Windows PowerShell)

### Prerequisites
- Python 3.11
- Node.js 18+
- Windows 11 (tested)

### Backend Setup

```powershell
cd d:\ResQNet\backend

# Create virtual environment (if not exists)
python -m venv .venv

# Activate
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.example .env
# Edit .env as needed

# Run database migrations
python -m alembic upgrade head

# Seed demo data
python ..\scripts\seed_full_demo.py

# Start the backend server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Setup

```powershell
cd d:\ResQNet\frontend

# Install dependencies (if not done)
npm install

# Configure environment
copy .env.example .env

# Start development server
npm run dev
```

Access the application at: http://localhost:5173

## Demo Credentials

| Role | Email | Password |
|------|-------|----------|
| Citizen | citizen@resqnet.demo | Demo1234! |
| Citizen 2 | citizen2@resqnet.demo | Demo1234! |
| Rescuer | rescuer@resqnet.demo | Demo1234! |
| Rescuer 2 | rescuer2@resqnet.demo | Demo1234! |
| Coordinator | coordinator@resqnet.demo | Demo1234! |
| Admin | admin@resqnet.demo | Demo1234! |

> **Note**: Demo credentials are for demonstration only. Never use in production.

## Architecture

- **Backend**: FastAPI + SQLAlchemy + SQLite (dev) / PostgreSQL (production)
- **Frontend**: React 18 + TypeScript + Vite + TailwindCSS
- **AI**: Optional Gemini API (deterministic fallback always active)
- **Storage**: Local filesystem (configurable)

## Features

### Stage 5 — AI Incident Intelligence
- Deterministic incident extraction from natural language
- Optional Gemini AI integration (requires API key)
- Voice audio upload (transcription requires Whisper API key)
- Duplicate detection with similarity scoring

### Stage 6 — Rescue Evidence & Verification
- Before/after photo evidence submission
- SHA-256 file integrity verification
- Coordinator verification workflow
- Responder reliability scores
- Persistent in-app notifications

### Stage 7 — Dashboards & Operations
- Role-specific dashboards (citizen/rescuer/coordinator/admin)
- Analytics with real database metrics
- Case progress tracking (EN_ROUTE → ARRIVED → RESCUE_IN_PROGRESS → RESCUED → VERIFIED)

### Stage 8 — Security & Quality
- JWT authentication with expiration
- Role-based access control
- File upload validation (MIME + signature)
- Input sanitization
- Audit event logging

## API Documentation

When running, visit: http://localhost:8000/docs

## Running Tests

```powershell
cd d:\ResQNet\backend
.\.venv\Scripts\Activate.ps1
python -m pytest tests/ -v
```

## Production Deployment

1. Set `ENVIRONMENT=production` in `.env`
2. Use a strong `SECRET_KEY` (run `python -c "import secrets; print(secrets.token_hex(32))"`)
3. Set `DATABASE_URL` to PostgreSQL connection string
4. Configure `CORS_ORIGINS` for your domain
5. Use a reverse proxy (nginx) in front of uvicorn
6. Run: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4`

## Known Limitations

- Voice transcription requires Whisper API key (optional)
- AI extraction fallback is deterministic (no ML model required)
- Image classification not implemented in this release
- PostgreSQL/PostGIS geographic search available but not used in routing (Haversine used instead)
- Background jobs run inline (no Celery/worker process required for demo)
