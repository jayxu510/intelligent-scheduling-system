"""Pydantic models for the scheduling system."""

from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field


class ShiftType(str, Enum):
    """Shift types matching frontend definitions."""
    DAY = "DAY"
    SLEEP = "SLEEP"
    MINI_NIGHT = "MINI_NIGHT"
    LATE_NIGHT = "LATE_NIGHT"
    VACATION = "VACATION"
    CUSTOM = "CUSTOM"
    NONE = "NONE"


class SlotType(str, Enum):
    """Specific slot types within shifts."""
    # Day shift slots
    DAY_REGULAR = "DAY_REGULAR"
    # Sleep shift slots
    SLEEP_CHIEF = "SLEEP_CHIEF"
    SLEEP_NORTHWEST = "SLEEP_NORTHWEST"
    SLEEP_SOUTHEAST = "SLEEP_SOUTHEAST"
    # Mini night slots
    MINI_NIGHT_CHIEF = "MINI_NIGHT_CHIEF"
    MINI_NIGHT_REGULAR = "MINI_NIGHT_REGULAR"
    # Late night slots
    LATE_NIGHT_CHIEF = "LATE_NIGHT_CHIEF"
    LATE_NIGHT_REGULAR = "LATE_NIGHT_REGULAR"


class EmployeeRole(str, Enum):
    """Employee roles."""
    LEADER = "LEADER"
    STAFF = "STAFF"


class Employee(BaseModel):
    """Employee model."""
    id: str
    name: str
    role: EmployeeRole
    title: Optional[str] = None
    avoidance_group_id: Optional[str] = None

    class Config:
        from_attributes = True


class ShiftRecord(BaseModel):
    """A single shift assignment."""
    employee_id: str
    date: str
    shift_type: ShiftType
    slot_type: Optional[SlotType] = None
    label: Optional[str] = None


class DailySchedule(BaseModel):
    """Schedule for a single day."""
    date: str
    day_of_week: str
    records: list[ShiftRecord]


class AvoidanceGroup(BaseModel):
    """Group of employees who should avoid being in the same shift."""
    id: str
    employee_ids: list[str]


class ScheduleConstraints(BaseModel):
    """Constraints for schedule generation."""
    avoidance_groups: list[AvoidanceGroup] = Field(default_factory=list)


class GenerateScheduleRequest(BaseModel):
    """Request body for schedule generation."""
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$", examples=["2024-10"])
    group_id: str = Field(..., pattern=r"^[ABC]$", examples=["A"])
    employees: list[Employee]
    constraints: ScheduleConstraints = Field(default_factory=ScheduleConstraints)


class GenerateScheduleResponse(BaseModel):
    """Response for schedule generation."""
    month: str
    group_id: str
    work_days: list[str]
    schedules: list[DailySchedule]
    statistics: dict


class ValidationError(BaseModel):
    """A single validation error."""
    error_type: str
    date: str
    message: str
    employee_ids: list[str] = Field(default_factory=list)


class ValidateScheduleRequest(BaseModel):
    """Request body for schedule validation."""
    date: str
    records: list[ShiftRecord]
    employees: list[Employee]
    constraints: ScheduleConstraints = Field(default_factory=ScheduleConstraints)


class ValidateScheduleResponse(BaseModel):
    """Response for schedule validation."""
    is_valid: bool
    errors: list[ValidationError]


class ExportScheduleRequest(BaseModel):
    """Request body for schedule export."""
    month: str
    group_id: str
    schedules: list[DailySchedule]
    employees: list[Employee]


# ============================================
# 新增：初始化数据相关模型
# ============================================

class EmployeeDTO(BaseModel):
    """员工数据传输对象"""
    id: int
    name: str
    is_night_leader: bool = False
    sequence_order: int = 0
    avoidance_group_id: Optional[int] = None

    class Config:
        from_attributes = True


class AvoidanceRuleDTO(BaseModel):
    """避让规则数据传输对象"""
    id: int
    name: Optional[str] = None
    member_ids: list[int] = Field(default_factory=list)
    description: Optional[str] = None

    class Config:
        from_attributes = True


class ShiftRecordDTO(BaseModel):
    """排班记录数据传输对象"""
    employee_id: int
    date: str
    shift_type: str
    seat_type: Optional[str] = None
    label: Optional[str] = None


class DailyScheduleDTO(BaseModel):
    """每日排班数据传输对象"""
    date: str
    day_of_week: str
    records: list[ShiftRecordDTO]


class InitDataRequest(BaseModel):
    """初始化数据请求"""
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$", examples=["2024-10"])
    group_id: str = Field(..., pattern=r"^[ABC]$", examples=["A"])


class InitDataResponse(BaseModel):
    """初始化数据响应"""
    month: str
    group_id: str
    work_days: list[str]
    employees: list[EmployeeDTO]
    schedules: list[DailyScheduleDTO]
    avoidance_rules: list[AvoidanceRuleDTO]
    anchor_date: str
    anchor_group: str


class AutoGenerateRequest(BaseModel):
    """自动排班请求"""
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$", examples=["2024-10"])
    group_id: str = Field(..., pattern=r"^[ABC]$", examples=["A"])
    start_date: Optional[str] = None  # 可选的开始日期
    end_date: Optional[str] = None    # 可选的结束日期
    locked_records: Optional[list[dict]] = None  # 新增：锁定的单元格记录


class AutoGenerateResponse(BaseModel):
    """自动排班响应（预览数据，不存库）"""
    month: str
    group_id: str
    work_days: list[str]
    schedules: list[DailyScheduleDTO]
    statistics: dict = Field(default_factory=dict)


class SaveScheduleRequest(BaseModel):
    """保存排班请求"""
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$", examples=["2024-10"])
    group_id: str = Field(..., pattern=r"^[ABC]$", examples=["A"])
    schedules: list[DailyScheduleDTO]


class SaveScheduleResponse(BaseModel):
    """保存排班响应"""
    success: bool
    message: str
    saved_count: int


class EmployeeCreateRequest(BaseModel):
    """创建员工请求"""
    name: str
    group_id: str = Field(..., pattern=r"^[ABC]$", description="所属组别")  # 新增
    is_night_leader: bool = False
    sequence_order: Optional[int] = None
    avoidance_group_id: Optional[int] = None


class EmployeeUpdateRequest(BaseModel):
    """更新员工请求"""
    name: Optional[str] = None
    group_id: Optional[str] = None  # 新增
    is_night_leader: Optional[bool] = None
    sequence_order: Optional[int] = None
    avoidance_group_id: Optional[int] = None


class SetFirstWorkDayRequest(BaseModel):
    """设置首个工作日请求"""
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$", examples=["2024-10"])
    group_id: str = Field(..., pattern=r"^[ABC]$", examples=["A"])
    first_work_day: int = Field(..., ge=1, le=31, examples=[1])


class SetFirstWorkDayResponse(BaseModel):
    """设置首个工作日响应"""
    success: bool
    message: str
    work_days: list[str]
    config_key: str


class UpdateShiftRequest(BaseModel):
    """更新单个班次请求"""
    employee_id: int
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", examples=["2024-10-15"])
    shift_type: str
    group_id: str = Field(..., pattern=r"^[ABC]$", examples=["A"])
    seat_type: Optional[str] = None
    label: Optional[str] = None


class UpdateShiftResponse(BaseModel):
    """更新单个班次响应"""
    success: bool
    message: str

