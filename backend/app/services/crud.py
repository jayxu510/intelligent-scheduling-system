"""
数据库 CRUD 操作服务
处理员工、排班、避让规则和系统配置的增删改查
"""
from datetime import date, datetime
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, delete

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from database.models import Employee, Shift, AvoidanceRule, SystemConfig


# ============================================
# 员工 CRUD
# ============================================

def get_all_employees(db: Session) -> list[Employee]:
    """获取所有员工，按 sequence_order 排序"""
    return db.query(Employee).order_by(Employee.sequence_order).all()


def get_employee_by_id(db: Session, employee_id: int) -> Optional[Employee]:
    """根据ID获取员工"""
    return db.query(Employee).filter(Employee.id == employee_id).first()


def create_employee(db: Session, name: str, group_id: str = 'A', is_night_leader: bool = False,
                    sequence_order: int = 0, avoidance_group_id: int = None) -> Employee:
    """创建新员工"""
    employee = Employee(
        name=name,
        group_id=group_id,
        is_night_leader=is_night_leader,
        sequence_order=sequence_order,
        avoidance_group_id=avoidance_group_id
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return employee


def update_employee(db: Session, employee_id: int, **kwargs) -> Optional[Employee]:
    """更新员工信息"""
    employee = get_employee_by_id(db, employee_id)
    if employee:
        for key, value in kwargs.items():
            if hasattr(employee, key):
                setattr(employee, key, value)
        db.commit()
        db.refresh(employee)
    return employee


def delete_employee(db: Session, employee_id: int) -> bool:
    """删除员工"""
    employee = get_employee_by_id(db, employee_id)
    if employee:
        db.delete(employee)
        db.commit()
        return True
    return False


# ============================================
# 排班记录 CRUD
# ============================================

def get_shifts_by_date_range(db: Session, start_date: date, end_date: date,
                              group_id: str = None) -> list[Shift]:
    """获取日期范围内的排班记录"""
    query = db.query(Shift).filter(
        and_(Shift.date >= start_date, Shift.date <= end_date)
    )
    if group_id:
        query = query.filter(Shift.group_id == group_id)
    return query.order_by(Shift.date, Shift.employee_id).all()


def get_shifts_by_month(db: Session, year: int, month: int, group_id: str = None) -> list[Shift]:
    """获取某月的排班记录"""
    from calendar import monthrange
    start_date = date(year, month, 1)
    end_date = date(year, month, monthrange(year, month)[1])
    return get_shifts_by_date_range(db, start_date, end_date, group_id)


def create_shift(db: Session, shift_date: date, group_id: str, employee_id: int,
                 shift_type: str, seat_type: str = None) -> Shift:
    """创建排班记录"""
    shift = Shift(
        date=shift_date,
        group_id=group_id,
        employee_id=employee_id,
        shift_type=shift_type,
        seat_type=seat_type
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift


def bulk_create_shifts(db: Session, shifts_data: list[dict]) -> list[Shift]:
    """批量创建排班记录"""
    shifts = [Shift(**data) for data in shifts_data]
    db.add_all(shifts)
    db.commit()
    for shift in shifts:
        db.refresh(shift)
    return shifts


def delete_shifts_by_date_range(db: Session, start_date: date, end_date: date,
                                 group_id: str = None) -> int:
    """删除日期范围内的排班记录"""
    query = delete(Shift).where(
        and_(Shift.date >= start_date, Shift.date <= end_date)
    )
    if group_id:
        query = query.where(Shift.group_id == group_id)
    result = db.execute(query)
    db.commit()
    return result.rowcount


def save_schedules(db: Session, schedules_data: list[dict], group_id: str) -> int:
    """
    保存排班数据（先删后插）
    schedules_data: [{"date": "2024-01-01", "employee_id": 1, "shift_type": "DAY", "seat_type": "REGULAR"}]
    """
    if not schedules_data:
        return 0

    # 获取日期范围
    dates = [datetime.strptime(s["date"], "%Y-%m-%d").date() if isinstance(s["date"], str) else s["date"]
             for s in schedules_data]
    start_date = min(dates)
    end_date = max(dates)

    # 删除旧数据
    delete_shifts_by_date_range(db, start_date, end_date, group_id)

    # 准备新数据
    shifts_to_create = []
    for data in schedules_data:
        shift_date = datetime.strptime(data["date"], "%Y-%m-%d").date() if isinstance(data["date"], str) else data["date"]
        shifts_to_create.append({
            "date": shift_date,
            "group_id": group_id,
            "employee_id": data["employee_id"],
            "shift_type": data["shift_type"],
            "seat_type": data.get("seat_type")
        })

    # 批量插入
    if shifts_to_create:
        bulk_create_shifts(db, shifts_to_create)

    return len(shifts_to_create)


def update_single_shift(db: Session, employee_id: int, shift_date: str, shift_type: str,
                       group_id: str, seat_type: Optional[str] = None) -> bool:
    """
    更新单个班次记录（实时保存）
    如果记录存在则更新，不存在则创建
    如果 shift_type 为 NONE，则删除记录
    """
    # 转换日期格式
    date_obj = datetime.strptime(shift_date, "%Y-%m-%d").date() if isinstance(shift_date, str) else shift_date

    # 查找现有记录
    existing_shift = db.query(Shift).filter(
        and_(
            Shift.employee_id == employee_id,
            Shift.date == date_obj,
            Shift.group_id == group_id
        )
    ).first()

    # 如果是 NONE 类型，删除记录
    if shift_type == "NONE":
        if existing_shift:
            db.delete(existing_shift)
            db.commit()
        return True

    # 更新或创建记录
    if existing_shift:
        existing_shift.shift_type = shift_type
        existing_shift.seat_type = seat_type
    else:
        new_shift = Shift(
            employee_id=employee_id,
            date=date_obj,
            shift_type=shift_type,
            group_id=group_id,
            seat_type=seat_type
        )
        db.add(new_shift)

    db.commit()
    return True


# ============================================
# 避让规则 CRUD
# ============================================

def get_all_avoidance_rules(db: Session) -> list[AvoidanceRule]:
    """获取所有避让规则"""
    return db.query(AvoidanceRule).filter(AvoidanceRule.is_active == True).all()


def get_avoidance_rule_by_id(db: Session, rule_id: int) -> Optional[AvoidanceRule]:
    """根据ID获取避让规则"""
    return db.query(AvoidanceRule).filter(AvoidanceRule.id == rule_id).first()


def create_avoidance_rule(db: Session, member_ids: list[int], name: str = None,
                           description: str = None) -> AvoidanceRule:
    """创建避让规则"""
    rule = AvoidanceRule(
        name=name,
        member_ids_json=member_ids,
        description=description,
        is_active=True
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def update_avoidance_rule(db: Session, rule_id: int, **kwargs) -> Optional[AvoidanceRule]:
    """更新避让规则"""
    rule = get_avoidance_rule_by_id(db, rule_id)
    if rule:
        for key, value in kwargs.items():
            if hasattr(rule, key):
                setattr(rule, key, value)
        db.commit()
        db.refresh(rule)
    return rule


def delete_avoidance_rule(db: Session, rule_id: int) -> bool:
    """删除避让规则（软删除）"""
    rule = get_avoidance_rule_by_id(db, rule_id)
    if rule:
        rule.is_active = False
        db.commit()
        return True
    return False


# ============================================
# 系统配置 CRUD
# ============================================

def get_system_config(db: Session, config_key: str) -> Optional[str]:
    """获取系统配置值"""
    config = db.query(SystemConfig).filter(SystemConfig.config_key == config_key).first()
    return config.config_value if config else None


def set_system_config(db: Session, config_key: str, config_value: str,
                      description: str = None) -> SystemConfig:
    """设置系统配置（存在则更新，不存在则创建）"""
    config = db.query(SystemConfig).filter(SystemConfig.config_key == config_key).first()
    if config:
        config.config_value = config_value
        if description:
            config.description = description
    else:
        config = SystemConfig(
            config_key=config_key,
            config_value=config_value,
            description=description
        )
        db.add(config)
    db.commit()
    db.refresh(config)
    return config


def get_anchor_config(db: Session) -> tuple[str, str]:
    """获取锚点配置（日期和组别）"""
    anchor_date = get_system_config(db, SystemConfig.ANCHOR_DATE) or "2024-01-01"
    anchor_group = get_system_config(db, SystemConfig.ANCHOR_GROUP) or "A"
    return anchor_date, anchor_group


def set_anchor_config(db: Session, anchor_date: str, anchor_group: str):
    """设置锚点配置"""
    set_system_config(db, SystemConfig.ANCHOR_DATE, anchor_date, "锚点日期")
    set_system_config(db, SystemConfig.ANCHOR_GROUP, anchor_group, "锚点组别")


# ============================================
# 工作日配置 CRUD
# ============================================

def get_work_day_config(db: Session, month: str, group_id: str) -> Optional[str]:
    """获取某月某组的首个工作日配置"""
    config_key = f"first_work_day_{month}_{group_id}"
    return get_system_config(db, config_key)


def set_work_day_config(db: Session, month: str, group_id: str, first_work_day: int) -> str:
    """设置某月某组的首个工作日"""
    config_key = f"first_work_day_{month}_{group_id}"
    config_value = str(first_work_day)
    set_system_config(db, config_key, config_value, f"{month} {group_id}组首个工作日")
    return config_key


def check_month_has_shifts(db: Session, year: int, month: int, group_id: str) -> bool:
    """检查某月是否已有排班数据"""
    shifts = get_shifts_by_month(db, year, month, group_id)
    return len(shifts) > 0
