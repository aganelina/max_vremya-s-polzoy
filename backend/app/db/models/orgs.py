import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, LargeBinary, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IdMixin
from app.db.enums import ORG_ROLE, ORG_STATUS, OrgRole, OrgStatus


class Org(IdMixin, CreatedAtMixin, Base):

    __tablename__ = "orgs"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    inn: Mapped[str | None] = mapped_column(String(12))
    contact_name: Mapped[str] = mapped_column(Text, nullable=False)
    contact_phone: Mapped[str] = mapped_column(Text, nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    district_id: Mapped[str | None] = mapped_column(ForeignKey("districts.id", ondelete="SET NULL"))
    status: Mapped[OrgStatus] = mapped_column(
        ORG_STATUS, nullable=False, server_default=OrgStatus.PENDING.value, index=True
    )
    reject_reason: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    sign_name: Mapped[str | None] = mapped_column(Text)
    sign_position: Mapped[str | None] = mapped_column(Text)
    seal_image: Mapped[bytes | None] = mapped_column(LargeBinary)
    signature_image: Mapped[bytes | None] = mapped_column(LargeBinary)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

class OrgMember(Base):
    __tablename__ = "org_members"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[OrgRole] = mapped_column(ORG_ROLE, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

class OrgInvite(IdMixin, CreatedAtMixin, Base):

    __tablename__ = "org_invites"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
