from datetime import date
from typing import Optional
from pydantic import BaseModel


class QueryRequest(BaseModel):
    question: str
    company_filter: Optional[str] = None


class SourceDoc(BaseModel):
    chunk_id: str
    company: str
    filing_date: date
    excerpt: str


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceDoc]
    retrieval_stats: dict
