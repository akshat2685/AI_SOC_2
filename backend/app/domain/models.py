from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Text, Enum, JSON, Boolean, Uuid, Time
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import enum
import datetime as dt
import uuid

class Base(DeclarativeBase):
    pass

class RoleEnum(str, enum.Enum):
    GLOBAL_ADMIN = "GLOBAL_ADMIN"
    TENANT_ADMIN = "TENANT_ADMIN"
    TENANT_ANALYST = "TENANT_ANALYST"
    TENANT_VIEWER = "TENANT_VIEWER"

class CriticalityEnum(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class SeverityEnum(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class StatusEnum(str, enum.Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"

class NotificationChannelEnum(str, enum.Enum):
    WEBSOCKET = "websocket"
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"

class NotificationStatusEnum(str, enum.Enum):
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD_LETTERED = "dead_lettered"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[List["User"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")
    incidents: Mapped[List["Incident"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")
    assets: Mapped[List["Asset"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")
    alerts: Mapped[List["Alert"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")
    api_keys: Mapped[List["ApiKey"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")
    notification_preferences: Mapped[List["NotificationPreference"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")
    webhook_endpoints: Mapped[List["WebhookEndpoint"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")
    notification_history: Mapped[List["NotificationHistory"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")
    key_store: Mapped[Optional["TenantKeyStore"]] = relationship(back_populates="tenant", cascade="all, delete-orphan", uselist=False)
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[RoleEnum] = mapped_column(Enum(RoleEnum))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tenant: Mapped[Optional[Tenant]] = relationship(back_populates="users")
    api_keys: Mapped[List["ApiKey"]] = relationship(back_populates="user", cascade="all, delete-orphan")

class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    hostname: Mapped[str] = mapped_column(String(255))
    ip_address: Mapped[str] = mapped_column(String(50))
    asset_type: Mapped[str] = mapped_column(String(100))
    criticality: Mapped[CriticalityEnum] = mapped_column(Enum(CriticalityEnum), default=CriticalityEnum.MEDIUM)

    tenant: Mapped[Tenant] = relationship(back_populates="assets")

class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[SeverityEnum] = mapped_column(Enum(SeverityEnum), default=SeverityEnum.MEDIUM)
    status: Mapped[StatusEnum] = mapped_column(Enum(StatusEnum), default=StatusEnum.OPEN)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tenant: Mapped[Tenant] = relationship(back_populates="incidents")
    alerts: Mapped[List["Alert"]] = relationship(back_populates="incident", cascade="all, delete-orphan")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    incident_id: Mapped[Optional[int]] = mapped_column(ForeignKey("incidents.id"), index=True)
    source: Mapped[str] = mapped_column(String(100))
    rule_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tenant: Mapped[Tenant] = relationship(back_populates="alerts")
    incident: Mapped[Optional[Incident]] = relationship(back_populates="alerts")

class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255))
    key_prefix: Mapped[str] = mapped_column(String(8), index=True, unique=True)
    key_hash: Mapped[str] = mapped_column(String(64), index=True, unique=True)
    scopes: Mapped[List[str]] = mapped_column(JSON, default=list)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tenant: Mapped[Tenant] = relationship(back_populates="api_keys")
    user: Mapped[User] = relationship(back_populates="api_keys")

class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    trace_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    action: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    integrity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    channel: Mapped[NotificationChannelEnum] = mapped_column(Enum(NotificationChannelEnum), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    min_severity: Mapped[SeverityEnum] = mapped_column(Enum(SeverityEnum), default=SeverityEnum.LOW)
    quiet_hours_start: Mapped[Optional[dt.time]] = mapped_column(Time, nullable=True)
    quiet_hours_end: Mapped[Optional[dt.time]] = mapped_column(Time, nullable=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)

    tenant: Mapped[Tenant] = relationship(back_populates="notification_preferences")

class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    secret: Mapped[str] = mapped_column(String(2048), nullable=False)
    events: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    tenant: Mapped[Tenant] = relationship(back_populates="webhook_endpoints")

class NotificationHistory(Base):
    __tablename__ = "notification_history"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    channel: Mapped[NotificationChannelEnum] = mapped_column(Enum(NotificationChannelEnum), nullable=False)
    event_type: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[NotificationStatusEnum] = mapped_column(Enum(NotificationStatusEnum), default=NotificationStatusEnum.DELIVERED)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tenant: Mapped[Tenant] = relationship(back_populates="notification_history")

class TenantKeyStore(Base):
    __tablename__ = "tenant_key_store"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False, unique=True)
    encrypted_dek: Mapped[str] = mapped_column(String(2048), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tenant: Mapped[Tenant] = relationship(back_populates="key_store")

class IntelligenceMetric(Base):
    __tablename__ = "intelligence_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    metric_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    dimensions: Mapped[dict] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tenant: Mapped[Tenant] = relationship()

class PlaybookStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

class ApprovalStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class Playbook(Base):
    __tablename__ = "playbooks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    definition: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tenant: Mapped[Tenant] = relationship()
    executions: Mapped[List["PlaybookExecution"]] = relationship(back_populates="playbook", cascade="all, delete-orphan")


class PlaybookExecution(Base):
    __tablename__ = "playbook_executions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    playbook_id: Mapped[int] = mapped_column(ForeignKey("playbooks.id"), index=True, nullable=False)
    status: Mapped[PlaybookStatusEnum] = mapped_column(Enum(PlaybookStatusEnum), default=PlaybookStatusEnum.PENDING)
    context_data: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant: Mapped[Tenant] = relationship()
    playbook: Mapped[Playbook] = relationship(back_populates="executions")
    approval_requests: Mapped[List["ApprovalRequest"]] = relationship(back_populates="execution", cascade="all, delete-orphan")


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    execution_id: Mapped[int] = mapped_column(ForeignKey("playbook_executions.id"), index=True, nullable=False)
    status: Mapped[ApprovalStatusEnum] = mapped_column(Enum(ApprovalStatusEnum), default=ApprovalStatusEnum.PENDING)
    requester_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    approver_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tenant: Mapped[Tenant] = relationship()
    execution: Mapped[PlaybookExecution] = relationship(back_populates="approval_requests")

class ComplianceFramework(Base):
    __tablename__ = "compliance_frameworks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tenant: Mapped[Tenant] = relationship()
    controls: Mapped[List["ComplianceControl"]] = relationship(back_populates="framework", cascade="all, delete-orphan")

class ComplianceControl(Base):
    __tablename__ = "compliance_controls"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    framework_id: Mapped[int] = mapped_column(ForeignKey("compliance_frameworks.id"), index=True, nullable=False)
    control_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    framework: Mapped[ComplianceFramework] = relationship(back_populates="controls")
    rules: Mapped[List["ComplianceRule"]] = relationship(back_populates="control", cascade="all, delete-orphan")

class ComplianceRule(Base):
    __tablename__ = "compliance_rules"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    control_id: Mapped[int] = mapped_column(ForeignKey("compliance_controls.id"), index=True, nullable=False)
    rule_expression: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    control: Mapped[ComplianceControl] = relationship(back_populates="rules")

class ComplianceViolationStatus(str, enum.Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    EXEMPTED = "EXEMPTED"

class ComplianceViolation(Base):
    __tablename__ = "compliance_violations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    rule_id: Mapped[int] = mapped_column(ForeignKey("compliance_rules.id"), index=True, nullable=False)
    asset_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    event_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[ComplianceViolationStatus] = mapped_column(Enum(ComplianceViolationStatus), default=ComplianceViolationStatus.OPEN)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tenant: Mapped[Tenant] = relationship()
    rule: Mapped[ComplianceRule] = relationship()
