from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class SearchQuery(BaseModel):
    keyword: str = ""        # должность / ключевое слово
    location: str = ""       # город (Алматы, Астана, Шымкент, ...)
    experience: str = ""     # опыт: any | no | 1-3 | 3-6 | 6+
    max_pages: int = 5
    strict_city: bool = True # отсеивать кандидатов из других городов


class Candidate(BaseModel):
    enbek_id: str
    position: str
    full_name: Optional[str] = None     # имя и фамилия (только при авторизации)
    phone: Optional[str] = None         # телефон (только при авторизации)
    name: Optional[str] = None          # пол, возраст
    city: Optional[str] = None
    salary: Optional[str] = None
    experience: Optional[str] = None    # общий стаж, напр. "3 года"
    work_history: Optional[str] = None  # места работы: компании, должности, периоды
    education: Optional[str] = None
    skills: Optional[str] = None
    languages: Optional[str] = None
    profile_url: str
    scraped_at: str = Field(default_factory=lambda: datetime.now().isoformat())
