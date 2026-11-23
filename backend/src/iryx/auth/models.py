"""IRYX Authentication and Identity ORM Models."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from iryx.db.base import Base


class MembershipRole(StrEnum):
    """Authorized RBAC roles for organization memberships."""

    ADMIN = "admin"
    ANALYST = "analyst"
    INVESTIGATOR = "investigator"
    VIEWER = "viewer"


class Organization(Base):
    """Organization entity representing customer tenants or security teams."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __init__(self, **kw) -> None:
        if kw.get("id") is None:
            kw["id"] = uuid.uuid4()
        super().__init__(**kw)

    def __repr__(self) -> str:
        return f"<Organization id={self.id!r} name={self.name!r}>"


class User(Base):
    """User account entity for authentication and access control."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __init__(self, **kw) -> None:
        if kw.get("id") is None:
            kw["id"] = uuid.uuid4()
        if kw.get("is_active") is None:
            kw["is_active"] = True
        super().__init__(**kw)

    def __repr__(self) -> str:
        return f"<User id={self.id!r} email={self.email!r} is_active={self.is_active!r}>"


class Membership(Base):
    """Membership association between a User and an Organization with an assigned role."""

    __tablename__ = "memberships"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    organization: Mapped["Organization"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(back_populates="memberships")

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "user_id",
            name="uq_memberships_organization_id_user_id",
        ),
        CheckConstraint(
            f"role IN ({', '.join(repr(r.value) for r in MembershipRole)})",
            name="ck_memberships_role_check",
        ),
    )

    @property
    def email(self) -> str | None:
        """Convenience property to access member user's email."""
        return self.user.email if self.user else None

    def __init__(self, **kw) -> None:
        if kw.get("id") is None:
            kw["id"] = uuid.uuid4()
        super().__init__(**kw)

    def __repr__(self) -> str:
        return (
            f"<Membership id={self.id!r} organization_id={self.organization_id!r} "
            f"user_id={self.user_id!r} role={self.role!r}>"
        )
