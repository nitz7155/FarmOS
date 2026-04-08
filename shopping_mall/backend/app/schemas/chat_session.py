from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


def to_camel(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(w.capitalize() for w in parts[1:])


class ChatSessionCreate(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    user_id: int


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_camel, populate_by_name=True)

    id: int
    user_id: int
    status: str
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime] = None
    message_count: Optional[int] = None
    message_preview: Optional[str] = None


class ChatSessionMessages(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    role: str
    text: str
    intent: Optional[str] = None
    escalated: Optional[bool] = None
    created_at: Optional[datetime] = None
