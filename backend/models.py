from __future__ import annotations
from datetime import date as DateType, datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict

class DataPointCreate(BaseModel):
    date: DateType
    value: float
    memo: str = Field(default='', max_length=500)

class DataPointUpdate(BaseModel):
    date: DateType | None = None
    value: float | None = None
    memo: str | None = Field(default=None, max_length=500)

class DataPoint(DataPointCreate):
    id: str

class Message(BaseModel):
    role: Literal['user','assistant','system','tool']
    content: str
    created_at: datetime | None = None

class ConversationCreate(BaseModel):
    title: str = Field(default='새 대화', max_length=120)
    messages: list[Message] = Field(default_factory=list)

class Conversation(BaseModel):
    id: str
    title: str
    messages: list[Message]
    created_at: datetime
    updated_at: datetime

class ChatRequest(BaseModel):
    analysis_target: Literal['region','personal'] = 'region'
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    region_id: str | None = None
    answer_mode: Literal['simple','basic','detail'] = 'basic'

class ChatResponse(BaseModel):
    resolved_region: dict[str, Any] | None = None
    region_candidates: list[dict[str, Any]] = Field(default_factory=list)
    analysis_target: str = 'region'
    answer: str
    conversation_id: str
    tools_used: list[dict[str, Any]] = Field(default_factory=list)
    charts: list[dict[str, Any]] = Field(default_factory=list)
    freshness: dict[str, Any] = Field(default_factory=dict)

class MonthlyRecord(BaseModel):
    model_config = ConfigDict(extra='allow')
    region_id: str
    month: str = Field(pattern=r'^\d{4}-\d{2}$')
    metrics: dict[str, Any] = Field(default_factory=dict)
    derived: dict[str, Any] = Field(default_factory=dict)
    indexes: dict[str, Any] = Field(default_factory=dict)
    freshness: dict[str, Any] = Field(default_factory=dict)

