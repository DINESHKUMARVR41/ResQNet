"""Stage 5 & 6: AI incident intelligence, evidence, verification, notifications."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0005_stage5_stage6"
down_revision = "0003_rescue_reliability"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # ---- Add columns to cases table ----
    case_cols = {c["name"] for c in inspector.get_columns("cases")}
    with op.batch_alter_table("cases") as batch:
        if "ai_extracted_data" not in case_cols:
            batch.add_column(sa.Column("ai_extracted_data", sa.Text(), nullable=True))
        if "voice_report_path" not in case_cols:
            batch.add_column(sa.Column("voice_report_path", sa.Text(), nullable=True))
        if "voice_transcription" not in case_cols:
            batch.add_column(sa.Column("voice_transcription", sa.Text(), nullable=True))
        if "verified_at" not in case_cols:
            batch.add_column(sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
        if "verified_by" not in case_cols:
            batch.add_column(sa.Column("verified_by", sa.Text(), nullable=True))
        if "verification_reason" not in case_cols:
            batch.add_column(sa.Column("verification_reason", sa.Text(), nullable=True))
        if "closed_at" not in case_cols:
            batch.add_column(sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
        if "assigned_responder_id" not in case_cols:
            batch.add_column(sa.Column(
                "assigned_responder_id", sa.String(36),
                sa.ForeignKey("responder_profiles.id", name="fk_cases_assigned_responder"),
                nullable=True
            ))

    # ---- Create rescue_evidence table ----
    if "rescue_evidence" not in existing_tables:
        op.create_table(
            "rescue_evidence",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
            sa.Column("responder_id", sa.String(36), sa.ForeignKey("responder_profiles.id"), nullable=False),
            sa.Column("evidence_type", sa.String(30), nullable=False),
            sa.Column("file_path", sa.String(500), nullable=True),
            sa.Column("file_hash", sa.String(64), nullable=True),
            sa.Column("file_size", sa.Integer(), nullable=True),
            sa.Column("mime_type", sa.String(80), nullable=True),
            sa.Column("rescue_notes", sa.Text(), nullable=True),
            sa.Column("animal_condition", sa.Text(), nullable=True),
            sa.Column("rescue_timestamp", sa.DateTime(timezone=True), nullable=True),
            sa.Column("gps_latitude", sa.Float(), nullable=True),
            sa.Column("gps_longitude", sa.Float(), nullable=True),
            sa.Column("destination", sa.Text(), nullable=True),
            sa.Column("handover_details", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_rescue_evidence_case_id", "rescue_evidence", ["case_id"])
        op.create_index("ix_rescue_evidence_responder_id", "rescue_evidence", ["responder_id"])

    # ---- Create responder_reliability_scores table ----
    if "responder_reliability_scores" not in existing_tables:
        op.create_table(
            "responder_reliability_scores",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("responder_id", sa.String(36), sa.ForeignKey("responder_profiles.id", ondelete="CASCADE"), nullable=False),
            sa.Column("total_assignments", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("accepted_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("declined_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("expired_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("completed_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("verified_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("avg_response_minutes", sa.Float(), nullable=True),
            sa.Column("reliability_score", sa.Float(), nullable=False, server_default="100.0"),
            sa.Column("score_explanation", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("responder_id", name="uq_responder_reliability_responder_id"),
        )
        op.create_index("ix_responder_reliability_scores_responder_id", "responder_reliability_scores", ["responder_id"])

    # ---- Create notifications table ----
    if "notifications" not in existing_tables:
        op.create_table(
            "notifications",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=True),
            sa.Column("event_type", sa.String(60), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("is_read", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
        op.create_index("ix_notifications_is_read", "notifications", ["is_read"])


def downgrade():
    op.drop_table("notifications")
    op.drop_table("responder_reliability_scores")
    op.drop_table("rescue_evidence")
    with op.batch_alter_table("cases") as batch:
        for col in ["ai_extracted_data", "voice_report_path", "voice_transcription",
                    "verified_at", "verified_by", "verification_reason", "closed_at", "assigned_responder_id"]:
            batch.drop_column(col)
