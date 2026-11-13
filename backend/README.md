# ResQNet Backend

## Local setup (PowerShell)
```powershell
cd backend
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

The default local database is SQLite for a zero-configuration first run. Set `DATABASE_URL` to a PostgreSQL URL to use PostgreSQL. The initial Alembic migration enables PostGIS and adds a GiST-indexed geography point column on PostgreSQL.

Demo accounts (development only; password for all is `ResQNetDemo!2026`):
- citizen@resqnet.demo
- rescuer@resqnet.demo
- coordinator@resqnet.demo
- admin@resqnet.demo

API docs: http://localhost:8000/docs
