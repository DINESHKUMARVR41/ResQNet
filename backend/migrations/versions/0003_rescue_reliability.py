"""Add responder matching, assignment offers and handoff foundation."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0003_rescue_reliability"
down_revision = "0002_case_reporting"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind(); inspector = inspect(bind)
    existing = {c["name"] for c in inspector.get_columns("responder_profiles")}
    user_columns = {c["name"] for c in inspector.get_columns("users")}
    if "organization_id" not in user_columns:
        with op.batch_alter_table("users") as batch:
            batch.add_column(sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", name="fk_users_organization"), nullable=True))
    case_columns = {c["name"] for c in inspector.get_columns("cases")}
    if "owner_organization_id" not in case_columns:
        with op.batch_alter_table("cases") as batch:
            batch.add_column(sa.Column("owner_organization_id", sa.String(36), sa.ForeignKey("organizations.id", name="fk_cases_owner_organization"), nullable=True))
    for col in [sa.Column("latitude", sa.Float(), nullable=True), sa.Column("longitude", sa.Float(), nullable=True)]:
        if col.name not in existing: op.add_column("responder_profiles", col)
    tables = set(inspect(bind).get_table_names())
    if "assignment_offers" not in tables:
        op.create_table("assignment_offers",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
            sa.Column("responder_id", sa.String(36), sa.ForeignKey("responder_profiles.id", ondelete="CASCADE"), nullable=False),
            sa.Column("attempt_no", sa.Integer(), nullable=False), sa.Column("status", sa.String(20), nullable=False),
            sa.Column("score", sa.Float(), nullable=False), sa.Column("distance_km", sa.Float(), nullable=True),
            sa.Column("offered_at", sa.DateTime(timezone=True), nullable=False), sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True), sa.Column("response_reason", sa.Text(), nullable=True),
            sa.UniqueConstraint("case_id", "responder_id", name="uq_case_responder_offer"))
        op.create_index("ix_assignment_offers_case_id", "assignment_offers", ["case_id"])
        op.create_index("ix_assignment_offers_responder_id", "assignment_offers", ["responder_id"])
        op.create_index("ix_assignment_offers_status", "assignment_offers", ["status"])
        op.create_index("ix_assignment_status_deadline", "assignment_offers", ["status", "deadline_at"])
    if "case_handoffs" not in tables:
        op.create_table("case_handoffs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
            sa.Column("from_organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True),
            sa.Column("to_organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("initiated_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("status", sa.String(20), nullable=False), sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True))
        op.create_index("ix_case_handoffs_case_id", "case_handoffs", ["case_id"])
        op.create_index("ix_case_handoffs_status", "case_handoffs", ["status"])
    # Upgrade the synthetic Stage 2/3 demo identities so the Stage 4 workflow works
    # on an existing local database as well as on a fresh install.
    op.execute(sa.text("UPDATE responder_profiles SET verified_at = CURRENT_TIMESTAMP, latitude = 11.6643, longitude = 78.1460 WHERE user_id IN (SELECT id FROM users WHERE email = 'rescuer@resqnet.demo') AND verified_at IS NULL"))
    op.execute(sa.text("UPDATE users SET organization_id = (SELECT id FROM organizations WHERE name = 'Salem Animal Welfare Network (DEMO)' LIMIT 1) WHERE email = 'coordinator@resqnet.demo' AND organization_id IS NULL"))

def downgrade():
    op.drop_table("case_handoffs"); op.drop_table("assignment_offers")
    with op.batch_alter_table("cases") as batch:
        batch.drop_column("owner_organization_id")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("organization_id")
    op.drop_column("responder_profiles", "longitude"); op.drop_column("responder_profiles", "latitude")
