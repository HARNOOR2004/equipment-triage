from typing import Literal
from pydantic import BaseModel, Field

EquipType = Literal["centrifugal_pump", "air_compressor", "conveyor_motor"]
Priority = Literal["low", "medium", "high", "critical"]

class ReadingIn(BaseModel):
    sensor_name: str = Field(min_length=1, max_length=50)
    value: float | None = None
    unit: str | None = None

class ReportCreate(BaseModel):
    equipment_type: EquipType
    identifier: str = Field(min_length=1, max_length=100)
    issue_description: str = Field(min_length=10)
    operating_events: list[str] = []
    readings: list[ReadingIn] = []

class AnalyzeIn(BaseModel):
    answers: dict[str, str] = {}

class FindingIn(BaseModel):
    kind: Literal["observation", "confirmed"]
    text: str = Field(min_length=3)
    evidence_refs: list[str] = []

class WorkOrderEdit(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = None
    priority: Priority | None = None
    steps: list[str] | None = None

class ApproveIn(BaseModel):
    override_reason: str | None = None

class RejectIn(BaseModel):
    reason: str = Field(min_length=3)