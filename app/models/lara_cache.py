"""Cache local des données LaraWeb (LNHB), pour ne pas dépendre d'un accès
réseau à chaque utilisation, et parce que ces données n'évoluent que très
rarement (CDC : "stockage local en cache SQLite")."""
from sqlalchemy import Column, Integer, String, Float, DateTime
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
from app.database import Base


class LaraCacheDB(Base):
    __tablename__ = "lara_cache"

    nuclide = Column(String(20), primary_key=True)  # ex: "Sr-90", format LaraWeb
    element = Column(String(50), nullable=True)
    z = Column(Integer, nullable=True)
    half_life_years = Column(Float, nullable=True)
    half_life_seconds = Column(Float, nullable=True)
    specific_activity_bq_g = Column(Float, nullable=True)
    reference = Column(String(255), nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class LaraCacheEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    nuclide: str
    element: Optional[str] = None
    z: Optional[int] = None
    half_life_years: Optional[float] = None
    half_life_seconds: Optional[float] = None
    specific_activity_bq_g: Optional[float] = None
    reference: Optional[str] = None
    fetched_at: datetime
