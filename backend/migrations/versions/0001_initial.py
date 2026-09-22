"""Начальная схема базы данных.

Revision ID: 0001
Revises:
Create Date: 2026-09-29 05:13:44.090374

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.create_table(
        "bot_updates",
        sa.Column("dedup_key", sa.Text(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("dedup_key", name=op.f("pk_bot_updates")),
    )
    op.create_table(
        "districts",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_districts")),
    )
    op.create_table(
        "jobs",
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column(
            "run_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_index(
        "ix_jobs_due", "jobs", ["run_at"], unique=False, postgresql_where=sa.text("done_at IS NULL")
    )
    op.create_table(
        "universities",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_universities")),
    )
    op.create_table(
        "district_adjacency",
        sa.Column("district_id", sa.String(length=32), nullable=False),
        sa.Column("neighbor_id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["district_id"],
            ["districts.id"],
            name=op.f("fk_district_adjacency_district_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["neighbor_id"],
            ["districts.id"],
            name=op.f("fk_district_adjacency_neighbor_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("district_id", "neighbor_id", name=op.f("pk_district_adjacency")),
    )
    op.create_table(
        "users",
        sa.Column("max_user_id", sa.BigInteger(), nullable=False),
        sa.Column("first_name", sa.Text(), server_default="", nullable=False),
        sa.Column("is_operator", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("onboarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("university_id", sa.String(length=32), nullable=True),
        sa.Column("district_id", sa.String(length=32), nullable=True),
        sa.Column(
            "interests",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column(
            "transport",
            sa.Enum("walk", "transit", "scooter", name="transport"),
            server_default="walk",
            nullable=False,
        ),
        sa.Column(
            "notify",
            sa.Enum("all", "mine", "pause", name="notify_mode"),
            server_default="all",
            nullable=False,
        ),
        sa.Column("pause_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("weekly_search", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["district_id"],
            ["districts.id"],
            name=op.f("fk_users_district_id"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["university_id"],
            ["universities.id"],
            name=op.f("fk_users_university_id"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("max_user_id", name=op.f("ux_users_max_user_id")),
    )
    op.create_table(
        "busy_slots",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.Text(), server_default="", nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_busy_slots_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_busy_slots")),
    )
    op.create_index(op.f("ix_busy_slots_user_id"), "busy_slots", ["user_id"], unique=False)
    op.create_table(
        "certificates",
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("code", sa.String(length=7), nullable=False),
        sa.Column("period", sa.Enum("semester", "all", name="cert_period"), nullable=False),
        sa.Column("rows", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("total", sa.Numeric(precision=6, scale=1), nullable=False),
        sa.Column("pdf_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_certificates_user_id"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_certificates")),
        sa.UniqueConstraint("code", name=op.f("ux_certificates_code")),
    )
    op.create_index(op.f("ix_certificates_user_id"), "certificates", ["user_id"], unique=False)
    op.create_table(
        "free_windows",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("after_label", sa.Text(), server_default="", nullable=False),
        sa.Column("place_label", sa.Text(), server_default="", nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_free_windows_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_free_windows")),
    )
    op.create_index(op.f("ix_free_windows_user_id"), "free_windows", ["user_id"], unique=False)
    op.create_table(
        "help_requests",
        sa.Column("author_id", sa.UUID(), nullable=False),
        sa.Column("text", sa.String(length=200), nullable=False),
        sa.Column("hours", sa.Numeric(precision=3, scale=1), nullable=False),
        sa.Column("when_label", sa.Text(), server_default="", nullable=False),
        sa.Column("district_id", sa.String(length=32), nullable=True),
        sa.Column(
            "status",
            sa.Enum("open", "matched", "closed", "cancelled", name="help_status"),
            server_default="open",
            nullable=False,
        ),
        sa.Column("helper_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("hours > 0", name=op.f("ck_help_requests_hours_positive")),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_help_requests_author_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["district_id"],
            ["districts.id"],
            name=op.f("fk_help_requests_district_id"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["helper_id"],
            ["users.id"],
            name=op.f("fk_help_requests_helper_id"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_help_requests")),
    )
    op.create_index(
        op.f("ix_help_requests_author_id"), "help_requests", ["author_id"], unique=False
    )
    op.create_table(
        "max_chats",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_max_chats_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_max_chats")),
    )
    op.create_table(
        "mentor_settings",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("accepting", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_mentor_settings_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_mentor_settings")),
    )
    op.create_table(
        "orgs",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("inn", sa.String(length=12), nullable=True),
        sa.Column("contact_name", sa.Text(), nullable=False),
        sa.Column("contact_phone", sa.Text(), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("district_id", sa.String(length=32), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "verified", "rejected", name="org_status"),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by", sa.UUID(), nullable=True),
        sa.Column("sign_name", sa.Text(), nullable=True),
        sa.Column("sign_position", sa.Text(), nullable=True),
        sa.Column("seal_image", sa.LargeBinary(), nullable=True),
        sa.Column("signature_image", sa.LargeBinary(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_orgs_created_by"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["district_id"], ["districts.id"], name=op.f("fk_orgs_district_id"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["verified_by"], ["users.id"], name=op.f("fk_orgs_verified_by"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orgs")),
    )
    op.create_index(op.f("ix_orgs_status"), "orgs", ["status"], unique=False)
    op.create_table(
        "schedules",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_schedules_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_schedules")),
    )
    op.create_table(
        "help_responses",
        sa.Column("request_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["help_requests.id"],
            name=op.f("fk_help_responses_request_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_help_responses_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("request_id", "user_id", name=op.f("pk_help_responses")),
    )
    op.create_index(op.f("ix_help_responses_user_id"), "help_responses", ["user_id"], unique=False)
    op.create_table(
        "hour_ledger",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "source",
            sa.Enum("shift", "micro", "bank_help", "bank_spend", name="ledger_source"),
            nullable=False,
        ),
        sa.Column("ref_id", sa.Uuid(), nullable=True),
        sa.Column("hours", sa.Numeric(precision=4, scale=1), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=True),
        sa.Column(
            "accepted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"], name=op.f("fk_hour_ledger_org_id"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_hour_ledger_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hour_ledger")),
    )
    op.create_index(
        "ix_hour_ledger_user_accepted", "hour_ledger", ["user_id", "accepted_at"], unique=False
    )
    op.create_index(
        "ux_hour_ledger_ref",
        "hour_ledger",
        ["user_id", "source", "ref_id"],
        unique=True,
        postgresql_where=sa.text("ref_id IS NOT NULL"),
    )
    op.create_table(
        "micro_tasks",
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("text", sa.String(length=1000), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("answers_needed", sa.Integer(), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "answers_needed > 0", name=op.f("ck_micro_tasks_answers_needed_positive")
        ),
        sa.CheckConstraint("minutes BETWEEN 5 AND 60", name=op.f("ck_micro_tasks_minutes_range")),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_micro_tasks_created_by"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"], name=op.f("fk_micro_tasks_org_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_micro_tasks")),
    )
    op.create_index(op.f("ix_micro_tasks_org_id"), "micro_tasks", ["org_id"], unique=False)
    op.create_table(
        "org_invites",
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_org_invites_created_by"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"], name=op.f("fk_org_invites_org_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_org_invites")),
        sa.UniqueConstraint("token", name=op.f("ux_org_invites_token")),
    )
    op.create_index(op.f("ix_org_invites_org_id"), "org_invites", ["org_id"], unique=False)
    op.create_table(
        "org_members",
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.Enum("owner", "coordinator", name="org_role"), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"], name=op.f("fk_org_members_org_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_org_members_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("org_id", "user_id", name=op.f("pk_org_members")),
    )
    op.create_index(op.f("ix_org_members_user_id"), "org_members", ["user_id"], unique=False)
    op.create_table(
        "shifts",
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "category",
            sa.Enum("people", "animals", "ecology", "books", "things", "online", name="category"),
            nullable=False,
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("quorum", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "place",
            sa.Enum("org", "district", "online", name="shift_place"),
            server_default="org",
            nullable=False,
        ),
        sa.Column("address", sa.Text(), server_default="", nullable=False),
        sa.Column("address_note", sa.Text(), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("district_id", sa.String(length=32), nullable=True),
        sa.Column("instructions", sa.Text(), server_default="", nullable=False),
        sa.Column("impact", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("open", "cancelled", "finished", name="shift_status"),
            server_default="open",
            nullable=False,
        ),
        sa.Column("checkin_secret", sa.LargeBinary(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("capacity > 0", name=op.f("ck_shifts_capacity_positive")),
        sa.CheckConstraint("ends_at > starts_at", name=op.f("ck_shifts_time_order")),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_shifts_created_by"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["district_id"],
            ["districts.id"],
            name=op.f("fk_shifts_district_id"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"], name=op.f("fk_shifts_org_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shifts")),
    )
    op.create_index(op.f("ix_shifts_org_id"), "shifts", ["org_id"], unique=False)
    op.create_index("ix_shifts_status_starts_at", "shifts", ["status", "starts_at"], unique=False)
    op.create_table(
        "companies",
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("picked_shift_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_companies_owner_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["picked_shift_id"],
            ["shifts.id"],
            name=op.f("fk_companies_picked_shift_id"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
        sa.UniqueConstraint("token", name=op.f("ux_companies_token")),
    )
    op.create_index(op.f("ix_companies_owner_id"), "companies", ["owner_id"], unique=False)
    op.create_table(
        "friend_invites",
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("shift_id", sa.UUID(), nullable=False),
        sa.Column("inviter_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["inviter_id"],
            ["users.id"],
            name=op.f("fk_friend_invites_inviter_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["shift_id"], ["shifts.id"], name=op.f("fk_friend_invites_shift_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_friend_invites")),
        sa.UniqueConstraint("token", name=op.f("ux_friend_invites_token")),
    )
    op.create_index(
        op.f("ix_friend_invites_inviter_id"), "friend_invites", ["inviter_id"], unique=False
    )
    op.create_table(
        "mentor_requests",
        sa.Column("newbie_id", sa.UUID(), nullable=False),
        sa.Column("shift_id", sa.UUID(), nullable=False),
        sa.Column("mentor_id", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("open", "accepted", "declined", "expired", name="mentor_request_status"),
            server_default="open",
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["mentor_id"],
            ["users.id"],
            name=op.f("fk_mentor_requests_mentor_id"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["newbie_id"],
            ["users.id"],
            name=op.f("fk_mentor_requests_newbie_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["shift_id"],
            ["shifts.id"],
            name=op.f("fk_mentor_requests_shift_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mentor_requests")),
    )
    op.create_index(
        op.f("ix_mentor_requests_newbie_id"), "mentor_requests", ["newbie_id"], unique=False
    )
    op.create_table(
        "messages",
        sa.Column("shift_id", sa.UUID(), nullable=False),
        sa.Column(
            "audience", sa.Enum("all", "waiting", "came", name="message_audience"), nullable=False
        ),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("sent_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_messages_created_by"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["shift_id"], ["shifts.id"], name=op.f("fk_messages_shift_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index(op.f("ix_messages_shift_id"), "messages", ["shift_id"], unique=False)
    op.create_table(
        "micro_answers",
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "taken", "sent", "accepted", "returned", "released", name="micro_answer_status"
            ),
            nullable=False,
        ),
        sa.Column("answer", sa.Text(), server_default="", nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            name=op.f("fk_micro_answers_reviewed_by"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["micro_tasks.id"],
            name=op.f("fk_micro_answers_task_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_micro_answers_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_micro_answers")),
    )
    op.create_index(op.f("ix_micro_answers_task_id"), "micro_answers", ["task_id"], unique=False)
    op.create_index(op.f("ix_micro_answers_user_id"), "micro_answers", ["user_id"], unique=False)
    op.create_index(
        "ux_micro_answers_one_taken",
        "micro_answers",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'taken'"),
    )
    op.create_table(
        "urgent_calls",
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("shift_id", sa.UUID(), nullable=False),
        sa.Column("what", sa.Text(), nullable=False),
        sa.Column("where_text", sa.Text(), nullable=False),
        sa.Column("start_in_min", sa.Integer(), nullable=False),
        sa.Column("people", sa.Integer(), nullable=False),
        sa.Column("reached", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_urgent_calls_created_by"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"], name=op.f("fk_urgent_calls_org_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["shift_id"], ["shifts.id"], name=op.f("fk_urgent_calls_shift_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_urgent_calls")),
    )
    op.create_index(op.f("ix_urgent_calls_org_id"), "urgent_calls", ["org_id"], unique=False)
    op.create_table(
        "bookings",
        sa.Column("shift_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "going",
                "checked_in",
                "done",
                "cancelled",
                "no_show",
                "manual",
                name="booking_status",
            ),
            server_default="going",
            nullable=False,
        ),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("company_id", sa.UUID(), nullable=True),
        sa.Column("via_invite_id", sa.UUID(), nullable=True),
        sa.Column("via_transfer_id", sa.UUID(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_bookings_company_id"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["shift_id"], ["shifts.id"], name=op.f("fk_bookings_shift_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_bookings_user_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["via_invite_id"],
            ["friend_invites.id"],
            name=op.f("fk_bookings_via_invite_id"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bookings")),
    )
    op.create_index(op.f("ix_bookings_shift_id"), "bookings", ["shift_id"], unique=False)
    op.create_index(op.f("ix_bookings_user_id"), "bookings", ["user_id"], unique=False)
    op.create_index(
        "ux_bookings_active",
        "bookings",
        ["shift_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'cancelled'"),
    )
    op.create_table(
        "company_members",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("window_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_company_members_company_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_company_members_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("company_id", "user_id", name=op.f("pk_company_members")),
    )
    op.create_index(
        op.f("ix_company_members_user_id"), "company_members", ["user_id"], unique=False
    )
    op.create_table(
        "message_relays",
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("participant_id", sa.UUID(), nullable=False),
        sa.Column("coordinator_id", sa.UUID(), nullable=True),
        sa.Column("participant_mid", sa.Text(), nullable=True),
        sa.Column("coordinator_mid", sa.Text(), nullable=True),
        sa.Column(
            "direction",
            sa.Enum("to_participant", "to_coordinator", name="relay_direction"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["coordinator_id"],
            ["users.id"],
            name=op.f("fk_message_relays_coordinator_id"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_message_relays_message_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["users.id"],
            name=op.f("fk_message_relays_participant_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message_relays")),
    )
    op.create_index(
        op.f("ix_message_relays_coordinator_mid"),
        "message_relays",
        ["coordinator_mid"],
        unique=False,
    )
    op.create_index(
        op.f("ix_message_relays_message_id"), "message_relays", ["message_id"], unique=False
    )
    op.create_index(
        op.f("ix_message_relays_participant_id"), "message_relays", ["participant_id"], unique=False
    )
    op.create_index(
        op.f("ix_message_relays_participant_mid"),
        "message_relays",
        ["participant_mid"],
        unique=False,
    )
    op.create_table(
        "urgent_recipients",
        sa.Column("call_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["call_id"],
            ["urgent_calls.id"],
            name=op.f("fk_urgent_recipients_call_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_urgent_recipients_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("call_id", "user_id", name=op.f("pk_urgent_recipients")),
    )
    op.create_index(
        op.f("ix_urgent_recipients_user_id"), "urgent_recipients", ["user_id"], unique=False
    )
    op.create_table(
        "seat_transfers",
        sa.Column("booking_id", sa.UUID(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum("open", "claimed", "expired", name="transfer_status"),
            server_default="open",
            nullable=False,
        ),
        sa.Column("claimed_by", sa.UUID(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["booking_id"],
            ["bookings.id"],
            name=op.f("fk_seat_transfers_booking_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["claimed_by"],
            ["users.id"],
            name=op.f("fk_seat_transfers_claimed_by"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_seat_transfers")),
        sa.UniqueConstraint("token", name=op.f("ux_seat_transfers_token")),
    )
    op.create_index(
        op.f("ix_seat_transfers_booking_id"), "seat_transfers", ["booking_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_bookings_via_transfer_id"),
        "bookings",
        "seat_transfers",
        ["via_transfer_id"],
        ["id"],
        ondelete="SET NULL",
    )

def downgrade() -> None:
    op.drop_constraint(op.f("fk_bookings_via_transfer_id"), "bookings", type_="foreignkey")
    op.drop_index(op.f("ix_seat_transfers_booking_id"), table_name="seat_transfers")
    op.drop_table("seat_transfers")
    op.drop_index(op.f("ix_urgent_recipients_user_id"), table_name="urgent_recipients")
    op.drop_table("urgent_recipients")
    op.drop_index(op.f("ix_message_relays_participant_mid"), table_name="message_relays")
    op.drop_index(op.f("ix_message_relays_participant_id"), table_name="message_relays")
    op.drop_index(op.f("ix_message_relays_message_id"), table_name="message_relays")
    op.drop_index(op.f("ix_message_relays_coordinator_mid"), table_name="message_relays")
    op.drop_table("message_relays")
    op.drop_index(op.f("ix_company_members_user_id"), table_name="company_members")
    op.drop_table("company_members")
    op.drop_index(
        "ux_bookings_active",
        table_name="bookings",
        postgresql_where=sa.text("status <> 'cancelled'"),
    )
    op.drop_index(op.f("ix_bookings_user_id"), table_name="bookings")
    op.drop_index(op.f("ix_bookings_shift_id"), table_name="bookings")
    op.drop_table("bookings")
    op.drop_index(op.f("ix_urgent_calls_org_id"), table_name="urgent_calls")
    op.drop_table("urgent_calls")
    op.drop_index(
        "ux_micro_answers_one_taken",
        table_name="micro_answers",
        postgresql_where=sa.text("status = 'taken'"),
    )
    op.drop_index(op.f("ix_micro_answers_user_id"), table_name="micro_answers")
    op.drop_index(op.f("ix_micro_answers_task_id"), table_name="micro_answers")
    op.drop_table("micro_answers")
    op.drop_index(op.f("ix_messages_shift_id"), table_name="messages")
    op.drop_table("messages")
    op.drop_index(op.f("ix_mentor_requests_newbie_id"), table_name="mentor_requests")
    op.drop_table("mentor_requests")
    op.drop_index(op.f("ix_friend_invites_inviter_id"), table_name="friend_invites")
    op.drop_table("friend_invites")
    op.drop_index(op.f("ix_companies_owner_id"), table_name="companies")
    op.drop_table("companies")
    op.drop_index("ix_shifts_status_starts_at", table_name="shifts")
    op.drop_index(op.f("ix_shifts_org_id"), table_name="shifts")
    op.drop_table("shifts")
    op.drop_index(op.f("ix_org_members_user_id"), table_name="org_members")
    op.drop_table("org_members")
    op.drop_index(op.f("ix_org_invites_org_id"), table_name="org_invites")
    op.drop_table("org_invites")
    op.drop_index(op.f("ix_micro_tasks_org_id"), table_name="micro_tasks")
    op.drop_table("micro_tasks")
    op.drop_index(
        "ux_hour_ledger_ref",
        table_name="hour_ledger",
        postgresql_where=sa.text("ref_id IS NOT NULL"),
    )
    op.drop_index("ix_hour_ledger_user_accepted", table_name="hour_ledger")
    op.drop_table("hour_ledger")
    op.drop_index(op.f("ix_help_responses_user_id"), table_name="help_responses")
    op.drop_table("help_responses")
    op.drop_table("schedules")
    op.drop_index(op.f("ix_orgs_status"), table_name="orgs")
    op.drop_table("orgs")
    op.drop_table("mentor_settings")
    op.drop_table("max_chats")
    op.drop_index(op.f("ix_help_requests_author_id"), table_name="help_requests")
    op.drop_table("help_requests")
    op.drop_index(op.f("ix_free_windows_user_id"), table_name="free_windows")
    op.drop_table("free_windows")
    op.drop_index(op.f("ix_certificates_user_id"), table_name="certificates")
    op.drop_table("certificates")
    op.drop_index(op.f("ix_busy_slots_user_id"), table_name="busy_slots")
    op.drop_table("busy_slots")
    op.drop_table("users")
    op.drop_table("district_adjacency")
    op.drop_table("universities")
    op.drop_index("ix_jobs_due", table_name="jobs", postgresql_where=sa.text("done_at IS NULL"))
    op.drop_table("jobs")
    op.drop_table("districts")
    op.drop_table("bot_updates")
    op.execute("DROP TYPE IF EXISTS booking_status")
    op.execute("DROP TYPE IF EXISTS category")
    op.execute("DROP TYPE IF EXISTS cert_period")
    op.execute("DROP TYPE IF EXISTS help_status")
    op.execute("DROP TYPE IF EXISTS ledger_source")
    op.execute("DROP TYPE IF EXISTS mentor_request_status")
    op.execute("DROP TYPE IF EXISTS message_audience")
    op.execute("DROP TYPE IF EXISTS micro_answer_status")
    op.execute("DROP TYPE IF EXISTS notify_mode")
    op.execute("DROP TYPE IF EXISTS org_role")
    op.execute("DROP TYPE IF EXISTS org_status")
    op.execute("DROP TYPE IF EXISTS relay_direction")
    op.execute("DROP TYPE IF EXISTS shift_place")
    op.execute("DROP TYPE IF EXISTS shift_status")
    op.execute("DROP TYPE IF EXISTS transfer_status")
    op.execute("DROP TYPE IF EXISTS transport")
