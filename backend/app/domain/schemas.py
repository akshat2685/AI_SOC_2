from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime, time
from typing import Optional, List, Dict, Any
from .models import SeverityEnum, StatusEnum, RoleEnum, CriticalityEnum, NotificationChannelEnum, NotificationStatusEnum

class TenantBase(BaseModel):
    name: str = Field(..., max_length=255)

class TenantCreate(TenantBase):
    pass

class TenantUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)

class Tenant(TenantBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class UserBase(BaseModel):
    email: str = Field(..., max_length=255)
    role: RoleEnum
    tenant_id: Optional[int] = None

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    email: Optional[str] = None
    role: Optional[RoleEnum] = None
    tenant_id: Optional[int] = None
    password: Optional[str] = None

class User(UserBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class AssetBase(BaseModel):
    hostname: str = Field(..., max_length=255)
    ip_address: str = Field(..., max_length=50)
    asset_type: str = Field(..., max_length=100)
    criticality: CriticalityEnum = CriticalityEnum.MEDIUM
    tenant_id: int

class AssetCreate(AssetBase):
    pass

class AssetUpdate(BaseModel):
    hostname: Optional[str] = None
    ip_address: Optional[str] = None
    asset_type: Optional[str] = None
    criticality: Optional[CriticalityEnum] = None

class Asset(AssetBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class AlertBase(BaseModel):
    source: str = Field(..., max_length=100)
    rule_name: str = Field(..., max_length=255)
    description: str
    tenant_id: int

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
    tenant_id: int

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

class ApiKeyBase(BaseModel):
    name: str = Field(..., max_length=255)
    scopes: List[str] = []
    expires_at: Optional[datetime] = None

class ApiKeyCreate(ApiKeyBase):
    pass

class ApiKeyUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    scopes: Optional[List[str]] = None
    is_active: Optional[bool] = None

class ApiKeyResponse(ApiKeyBase):
    id: str # UUID converted to string
    key_prefix: str
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime]
    revoked_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)

class ApiKeyCreateResponse(ApiKeyResponse):
    raw_key: str # Returned ONLY on creation

class NotificationPreferenceBase(BaseModel):
    channel: NotificationChannelEnum
    enabled: bool = True
    min_severity: SeverityEnum = SeverityEnum.LOW
    quiet_hours_start: Optional[time] = None
    quiet_hours_end: Optional[time] = None
    config: dict = Field(default_factory=dict)
    tenant_id: int

class NotificationPreferenceCreate(NotificationPreferenceBase):
    pass

class NotificationPreferenceUpdate(BaseModel):
    enabled: Optional[bool] = None
    min_severity: Optional[SeverityEnum] = None
    quiet_hours_start: Optional[time] = None
    quiet_hours_end: Optional[time] = None
    config: Optional[dict] = None

class NotificationPreference(NotificationPreferenceBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class WebhookEndpointBase(BaseModel):
    url: str
    events: List[str] = Field(default_factory=list)
    is_active: bool = True
    tenant_id: int

class WebhookEndpointCreate(WebhookEndpointBase):
    secret: str

class WebhookEndpointUpdate(BaseModel):
    url: Optional[str] = None
    secret: Optional[str] = None
    events: Optional[List[str]] = None
    is_active: Optional[bool] = None

class WebhookEndpoint(WebhookEndpointBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class NotificationHistoryBase(BaseModel):
    channel: NotificationChannelEnum
    event_type: str
    payload: dict = Field(default_factory=dict)
    status: NotificationStatusEnum = NotificationStatusEnum.DELIVERED
    attempts: int = 1
    error: Optional[str] = None
    delivered_at: Optional[datetime] = None
    tenant_id: int

class NotificationHistory(NotificationHistoryBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class AuditEventBase(BaseModel):
    action: str = Field(..., max_length=255)
    details: dict = Field(default_factory=dict)
    trace_id: Optional[str] = None
    tenant_id: int
    user_id: Optional[int] = None

class AuditEventCreate(AuditEventBase):
    integrity_hash: str

class AuditEventUpdate(BaseModel):
    action: Optional[str] = None
    details: Optional[dict] = None

class AuditEventSchema(AuditEventBase):
    id: int
    integrity_hash: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class IntelligenceMetricBase(BaseModel):
    metric_name: str = Field(..., max_length=255)
    metric_value: float
    dimensions: dict = Field(default_factory=dict)
    tenant_id: int

class IntelligenceMetricCreate(IntelligenceMetricBase):
    pass

class IntelligenceMetricUpdate(BaseModel):
    metric_name: Optional[str] = None
    metric_value: Optional[float] = None
    dimensions: Optional[dict] = None

class IntelligenceMetric(IntelligenceMetricBase):
    id: int
    timestamp: datetime
    model_config = ConfigDict(from_attributes=True)

