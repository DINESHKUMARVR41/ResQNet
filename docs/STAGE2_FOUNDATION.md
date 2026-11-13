# Stage 2 — Foundation

## Delivered in this stage
- FastAPI application, health endpoint and OpenAPI docs.
- SQLAlchemy entities for users, organizations, responder profiles, skills, availability and cases.
- JWT bearer authentication, password hashing with PBKDF2-HMAC-SHA256, and role guards.
- Public registration restricted to citizen/rescuer; coordinator/admin are seeded only in development.
- Dashboard summary reads aggregate values from the database.
- Alembic environment and initial migration; PostgreSQL migration enables PostGIS and adds a GiST-indexed geography column.
- React/TypeScript/Vite frontend with login, registration, role-specific workspace shell and database-backed metrics.
- Synthetic Salem demo accounts.

## Important implementation notes
- Local default is SQLite to make first boot possible without installing PostgreSQL. Set `DATABASE_URL` to PostgreSQL to use the target database.
- `Base.metadata.create_all()` is currently used at application startup for developer convenience. For deployed environments, run Alembic migrations and disable startup schema creation in the next hardening pass.
- JWT tokens are stored in localStorage in this hackathon development foundation. Before production, move to secure HttpOnly cookies or a carefully designed refresh-token flow with CSRF protections.
- PostGIS is added to PostgreSQL via migration; the application stores latitude/longitude scalar fields as the portable model representation.
- No live AI, SMS, NGO integration or rescue operation is claimed.
