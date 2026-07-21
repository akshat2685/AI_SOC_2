import datetime
from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship

try:
    from core.repository import TenantBase
except ImportError:
    from intelligence_engine.core.repository import TenantBase

class ThreatFeed(TenantBase):
    __tablename__ = "threat_feeds"
    
    id = Column(String(50), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    url = Column(String(255), nullable=True)
    description = Column(String(255), nullable=True)
    provider = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), onupdate=lambda: datetime.datetime.now(datetime.timezone.utc))
    
    indicators = relationship("Indicator", back_populates="feed", cascade="all, delete-orphan")

class Indicator(TenantBase):
    __tablename__ = "threat_indicators"
    
    id = Column(String(100), primary_key=True, index=True)
    feed_id = Column(String(50), ForeignKey("threat_feeds.id"), nullable=True)
    indicator_type = Column(String(50), nullable=False, index=True) # e.g. ipv4, md5, url
    indicator_value = Column(String(255), nullable=False, index=True)
    confidence = Column(Integer, default=50)
    severity = Column(String(50), nullable=True)
    tlp = Column(String(20), nullable=True) # traffic light protocol
    valid_from = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    valid_until = Column(DateTime, nullable=True)
    raw_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    
    feed = relationship("ThreatFeed", back_populates="indicators")
