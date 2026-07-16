from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from core.repository import TenantBase

class Alert(TenantBase):
    __tablename__ = 'alerts'

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=func.now())
    title = Column(String(255), nullable=False)
    severity = Column(String(50), nullable=False)
    confidence = Column(String(50))
    confidence_score = Column(Integer)
    attack_type = Column(String(100))
    evidence = Column(Text)
    attacker_ip = Column(String(100))
    verdict = Column(String(50))
    incident_id = Column(Integer)
