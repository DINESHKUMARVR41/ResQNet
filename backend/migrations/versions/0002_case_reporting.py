"""Add reporting fields and case event timeline."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0002_case_reporting"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None

COLUMNS = [
    sa.Column("landmark", sa.String(240), nullable=True),
    sa.Column("address_text", sa.String(400), nullable=True),
    sa.Column("reporter_phone", sa.String(30), nullable=True),
    sa.Column("ai_summary", sa.Text(), nullable=True),
    sa.Column("triage_reason", sa.Text(), nullable=True),
    sa.Column("triage_confidence", sa.Float(), nullable=True),
    sa.Column("needs_human_review", sa.Boolean(), nullable=False, server_default=sa.true()),
    sa.Column("photo_path", sa.String(500), nullable=True),
    sa.Column("photo_content_type", sa.String(80), nullable=True),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
]

def upgrade():
    inspector = inspect(op.get_bind())
    existing = {c["name"] for c in inspector.get_columns("cases")}
    for column in COLUMNS:
        if column.name not in existing:
            op.add_column("cases", column)
    # Create new timeline table without disturbing existing foundation data.
    if "case_events" not in inspect(op.get_bind()).get_table_names():
        op.create_table(
            "case_events",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
            sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("event_type", sa.String(50), nullable=False),
            sa.Column("from_status", sa.String(40), nullable=True),
            sa.Column("to_status", sa.String(40), nullable=True),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_case_events_case_id", "case_events", ["case_id"])
        op.create_index("ix_case_events_case_created", "case_events", ["case_id", "created_at"])

def downgrade():
    op.drop_index("ix_case_events_case_created", table_name="case_events")
    op.drop_index("ix_case_events_case_id", table_name="case_events")
    op.drop_table("case_events")
    for column in reversed(COLUMNS):
        op.drop_column("cases", column.name)
