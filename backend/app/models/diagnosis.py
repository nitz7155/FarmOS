from datetime import datetime, timezone
from sqlalchemy import Integer, String, Text, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

class DiagnosisHistory(Base):
    __tablename__ = "diagnosis_histories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("users.id"), nullable=False
    )
    
    # 진단 정보
    pest: Mapped[str] = mapped_column(String(50), nullable=False)
    crop: Mapped[str] = mapped_column(String(50), nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # AI 분석 결과 (JSON 형태로 저장 - 방제법, 농약, 날씨 등)
    # 나중에 실제 RAG 결과 구조를 그대로 담기 위함
    analysis_result: Mapped[dict] = mapped_column(JSON, nullable=True)
    
    # 메타데이터
    image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "pest": self.pest,
            "crop": self.crop,
            "region": self.region,
            "analysis_result": self.analysis_result,
            "image_url": self.image_url,
            "date": self.created_at.strftime("%Y-%m-%d %H:%M"),
        }

class DiagnosisChatMessage(Base):
    __tablename__ = "diagnosis_chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    diagnosis_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("diagnosis_histories.id", ondelete="CASCADE"), nullable=False
    )
    
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # 'user' 또는 'assistant'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "diagnosis_id": self.diagnosis_id,
            "role": self.role,
            "content": self.content,
            "date": self.created_at.strftime("%Y-%m-%d %H:%M"),
        }
