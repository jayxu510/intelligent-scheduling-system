"""
SQLAlchemy 数据库模型定义
包含：employees, shifts, avoidance_rules, system_config 表
"""
from datetime import date, datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, Date, DateTime,
    ForeignKey, Text, JSON, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from .config import Base


class Employee(Base):
    """
    员工表
    存储员工基本信息和排序顺序
    """
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="员工ID")
    name = Column(String(50), nullable=False, comment="姓名")
    group_id = Column(String(1), nullable=False, default='A', comment="所属组别: A/B/C")
    is_night_leader = Column(Boolean, default=False, comment="是否夜班长/主任资质(前6列)")
    sequence_order = Column(Integer, nullable=False, default=0, comment="前端列排序顺序")
    avoidance_group_id = Column(Integer, ForeignKey("avoidance_rules.id", ondelete="SET NULL"),
                                nullable=True, comment="避让规则组ID")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    # 关联关系
    shifts = relationship("Shift", back_populates="employee", cascade="all, delete-orphan")
    avoidance_rule = relationship("AvoidanceRule", back_populates="employees")

    __table_args__ = (
        Index("idx_employee_sequence", "sequence_order"),
        {"comment": "员工信息表"}
    )


class Shift(Base):
    """
    排班记录表
    存储每日每人的排班信息
    """
    __tablename__ = "shifts"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="排班记录ID")
    date = Column(Date, nullable=False, comment="日期")
    group_id = Column(String(1), nullable=False, comment="组别: A/B/C")
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"),
                         nullable=False, comment="员工ID")
    shift_type = Column(String(20), nullable=False, comment="班次类型: DAY/SLEEP/MINI_NIGHT/LATE_NIGHT/VACATION/NONE")
    seat_type = Column(String(20), nullable=True, comment="席位类型: CHIEF/NORTHWEST/SOUTHEAST/REGULAR等")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    # 关联关系
    employee = relationship("Employee", back_populates="shifts")

    __table_args__ = (
        UniqueConstraint("date", "group_id", "employee_id", name="uq_shift_date_group_employee"),
        Index("idx_shift_date", "date"),
        Index("idx_shift_date_group", "date", "group_id"),
        Index("idx_shift_employee", "employee_id"),
        {"comment": "排班记录表"}
    )


class AvoidanceRule(Base):
    """
    避让规则表
    存储互斥成员的规则，同组成员不应在同一班次
    """
    __tablename__ = "avoidance_rules"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="规则ID")
    name = Column(String(50), nullable=True, comment="规则名称")
    member_ids_json = Column(JSON, nullable=False, comment="互斥成员ID列表JSON")
    description = Column(Text, nullable=True, comment="规则说明")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    # 关联关系
    employees = relationship("Employee", back_populates="avoidance_rule")

    __table_args__ = (
        {"comment": "避让规则表"}
    )


class SystemConfig(Base):
    """
    系统配置表
    存储锚点日期和锚点组别等系统级配置
    """
    __tablename__ = "system_config"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="配置ID")
    config_key = Column(String(50), unique=True, nullable=False, comment="配置键")
    config_value = Column(String(255), nullable=False, comment="配置值")
    description = Column(Text, nullable=True, comment="配置说明")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    __table_args__ = (
        {"comment": "系统配置表"}
    )

    # 预定义的配置键常量
    ANCHOR_DATE = "anchor_date"      # 锚点日期，如 "2024-01-01"
    ANCHOR_GROUP = "anchor_group"    # 锚点组别，如 "A"
