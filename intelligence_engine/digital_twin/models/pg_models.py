from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import declarative_base
from datetime import datetime, timezone

Base = declarative_base()

class DigitalTwinSnapshot(Base):
    __tablename__ = "digital_twin_snapshots"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, index=True, nullable=False)
    snapshot_hash = Column(String(255), index=True, nullable=False)
    node_count = Column(Integer, default=0)
    edge_count = Column(Integer, default=0)
    posture_score = Column(Float, default=100.0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class AttackPath(Base):
    __tablename__ = "digital_twin_attack_paths"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, index=True, nullable=False)
    snapshot_id = Column(Integer, ForeignKey("digital_twin_snapshots.id", ondelete="CASCADE"))
    source_asset_id = Column(String(255), nullable=False)
    target_asset_id = Column(String(255), nullable=False)
    path_length = Column(Integer, nullable=False)
    vulnerability_chain = Column(JSON, default=list)
    exposure_probability = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class SimulationRun(Base):
    __tablename__ = "digital_twin_simulation_runs"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, index=True, nullable=False)
    scenario_name = Column(String(255), nullable=False)
    parameters = Column(JSON, default=dict)
    results = Column(JSON, default=dict)
    impact_dollar_value = Column(Float, default=0.0)
    run_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
