from datetime import date, datetime, timezone

from sqlalchemy import String, Float, Integer, Date
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(10), nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    location: Mapped[str] = mapped_column(String(100), default="")
    area: Mapped[float] = mapped_column(Float, default=0.0)
    farmname: Mapped[str] = mapped_column(String(40), default="")
    profile: Mapped[str] = mapped_column(String(255), default="")
    create_at: Mapped[date] = mapped_column(
        Date, default=lambda: datetime.now(timezone.utc).date()
    )
    status: Mapped[int] = mapped_column(Integer, default=1)
