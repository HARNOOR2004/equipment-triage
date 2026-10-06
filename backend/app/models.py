from datetime import datetime, timezone
from sqlalchemy import String, Text, Float, ForeignKey, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base

def now():
    return datetime.now(timezone.utc)

class Equipment(Base):
    __tablename__ = "equipment"
    id: Mapped[int] = mapped_column(primary_key=True)
    equipment_type: Mapped[str] = mapped_column(String(50))
    identifier: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    reports: Mapped[list["Report"]] = relationship(back_populates="equipment")

class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"))
    issue_description: Mapped[str] = mapped_column(Text)
    operating_events: Mapped[list] = mapped_column(JSON, default=list)  # [{"id":"E1","text":"..."}]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    equipment: Mapped[Equipment] = relationship(back_populates="reports")
    sensors: Mapped[list["SensorReading"]] = relationship(back_populates="report", cascade="all, delete-orphan")

class SensorReading(Base):
    __tablename__ = "sensor_readings"
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"))
    sensor_name: Mapped[str] = mapped_column(String(50))   # temperature, vibration, pressure...
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    report: Mapped[Report] = relationship(back_populates="sensors")

class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"))
    status: Mapped[str] = mapped_column(String(20))        # success | partial | failed
    threshold_results: Mapped[list] = mapped_column(JSON, default=list)
    retrieved_chunks: Mapped[list] = mapped_column(JSON, default=list)
    ai_output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"))
    kind: Mapped[str] = mapped_column(String(20))          # observation | possible_cause | confirmed
    text: Mapped[str] = mapped_column(Text)
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(20))        # system | ai | technician
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class WorkOrder(Base):
    __tablename__ = "work_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"))
    analysis_id: Mapped[int | None] = mapped_column(ForeignKey("analyses.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20))      # low | medium | high | critical
    steps: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | approved | rejected
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[int] = mapped_column()
    action: Mapped[str] = mapped_column(String(50))
    actor: Mapped[str] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)