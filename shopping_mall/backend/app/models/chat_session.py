from datetime import datetime
from sqlalchemy import Integer, String, ForeignKey, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ChatSession(Base):
    __tablename__ = "shop_chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("shop_users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    # Ensure only one active session per user (partial unique index)
    __table_args__ = (
        Index(
            "idx_user_active_session",
            user_id,
            unique=True,
            postgresql_where="status = 'active'",
        ),
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    logs = relationship("ChatLog", back_populates="session")
