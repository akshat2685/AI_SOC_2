from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional, List
from .models import SeverityEnum, StatusEnum

class AlertBase(BaseModel):
    source: str = Field(..., max_length=100)
    rule_name: str = Field(..., max_length=255)
    description: str

class AlertCreate(AlertBase):
    incident_id: Optional[int] = None

class Alert(AlertBase):
    id: int
    incident_id: Optional[int]
    timestamp: datetime
    
    model_config = ConfigDict(from_attributes=True)


class IncidentBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str
    severity: SeverityEnum = SeverityEnum.MEDIUM
    status: StatusEnum = StatusEnum.OPEN

class IncidentCreate(IncidentBase):
    pass

class IncidentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    severity: Optional[SeverityEnum] = None
    status: Optional[StatusEnum] = None

class Incident(IncidentBase):
    id: int
    created_at: datetime
    updated_at: datetime
    alerts: List[Alert] = []

    model_config = ConfigDict(from_attributes=True)
