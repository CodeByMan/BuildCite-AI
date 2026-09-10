from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=4000)
    top_k: int = Field(default=6, ge=1, le=30)
    max_tokens: int = Field(default=800, ge=64, le=4096)
    save_to_history: bool = True
    page_numbers: list[int] | None = Field(
        default=None,
        max_length=100,
        description="Optional whitelist of pages to search within.",
    )

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        question = value.strip()
        if len(question) < 3:
            raise ValueError("Question must contain at least three non-whitespace characters.")
        return question

    @field_validator("page_numbers")
    @classmethod
    def validate_page_numbers(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        if any(page < 1 for page in value):
            raise ValueError("Page numbers must be positive integers.")
        return sorted(set(value))


class CitationOut(BaseModel):
    chunk_id: str
    page_number: int
    score: float
    excerpt: str


class QueryResponse(BaseModel):
    document_id: str
    question: str
    answer: str
    citations: list[CitationOut]
    input_tokens: int | None = None
    output_tokens: int | None = None
    created_at: datetime


class ChatMessageOut(BaseModel):
    role: str
    content: str
    created_at: datetime
    metadata: dict | None = None


class ChatHistoryOut(BaseModel):
    document_id: str
    history: list[ChatMessageOut]
