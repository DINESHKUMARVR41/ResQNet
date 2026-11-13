"""Create initial ResQNet foundation tables."""
from alembic import op
from app.core.database import Base
from app.models import *
revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None
def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    if bind.dialect.name == "postgresql":
        bind.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS postgis")
        bind.exec_driver_sql("ALTER TABLE cases ADD COLUMN IF NOT EXISTS location geography(Point, 4326)")
        bind.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_cases_location_gist ON cases USING GIST (location)")
def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.exec_driver_sql("DROP INDEX IF EXISTS ix_cases_location_gist")
        bind.exec_driver_sql("ALTER TABLE cases DROP COLUMN IF EXISTS location")
    Base.metadata.drop_all(bind=bind)
