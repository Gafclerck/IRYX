"""IRYX Authentication and Identity ORM Models."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from iryx.db.base import Base


class User(Base):
    """User account entity for authentication and access control."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
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

    def __init__(self, **kw) -> None:
        kw.setdefault("id", uuid.uuid4())
        kw.setdefault("is_active", True)
        super().__init__(**kw)

    def __repr__(self) -> str:
        return (
            f"<User id={self.id!r} email={self.email!r} is_active={self.is_active!r}>"
        )
