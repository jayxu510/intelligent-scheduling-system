"""API routes for scheduling operations."""

from datetime import datetime
from calendar import monthrange
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from database.config import get_db
from database.models import Employee as EmployeeModel, Shift, AvoidanceRule, SystemConfig

from app.models.schemas import (
    GenerateScheduleRequest,
    GenerateScheduleResponse,
    ValidateScheduleRequest,
    ValidateScheduleResponse,
    ExportScheduleRequest,
    Employee,
    EmployeeRole,
    ShiftRecord,
    DailySchedule,
    ScheduleConstraints,
    AvoidanceGroup,
    ShiftType,
    # 新增模型
    InitDataResponse,
    AutoGenerateRequest,
    AutoGenerateResponse,
    SaveScheduleRequest,
    SaveScheduleResponse,
    EmployeeDTO,
    AvoidanceRuleDTO,
    ShiftRecordDTO,
    DailyScheduleDTO,
    EmployeeCreateRequest,
    EmployeeUpdateRequest,
    SetFirstWorkDayRequest,
    SetFirstWorkDayResponse,
    UpdateShiftRequest,
    UpdateShiftResponse,
)
from app.services.scheduler import SchedulingSolver
from app.services.validator import validate_daily_schedule
from app.services.exporter import export_schedule_to_excel
from app.services.crud import (
    get_all_employees,
    get_all_avoidance_rules,
    get_shifts_by_month,
    save_schedules,
    update_single_shift,
    get_anchor_config,
    create_employee,
    update_employee,
    delete_employee,
    get_work_day_config,
    set_work_day_config,
    check_month_has_shifts,
)
from app.utils.date_utils import parse_month, get_work_days_in_month, get_day_of_week_cn, generate_work_days_from_first_day


router = APIRouter(prefix="/api", tags=["schedule"])


# ============================================
# 新增接口：初始化数据
# ============================================

@router.get("/init-data", response_model=InitDataResponse)
async def get_init_data(month: str, group_id: str, db: Session = Depends(get_db)):
    """
    获取初始化数据

    读取 system_config 计算该月工作日 -> 查询 shifts 表填充数据
    -> 若无数据则返回空结构 -> 同时返回 employees 和 rules

    Args:
        month: 月份，格式 YYYY-MM
        group_id: 组别 A/B/C
        db: 数据库会话

    Returns:
        InitDataResponse: 包含员工、排班、避让规则等初始数据
    """
    try:
        # 验证参数
        if group_id not in ['A', 'B', 'C']:
            raise HTTPException(status_code=400, detail="group_id must be A, B, or C")

        # 解析月份
        year, month_num = parse_month(month)

        # 获取锚点配置
        try:
            anchor_date, anchor_group = get_anchor_config(db)
        except Exception:
            # 数据库连接失败时使用默认值
            anchor_date, anchor_group = "2024-01-01", "A"

        # 检查是否已设置该月工作日配置
        try:
            first_work_day_config = get_work_day_config(db, month, group_id)
            has_shifts = check_month_has_shifts(db, year, month_num, group_id)
        except Exception:
            # 数据库失败时
            first_work_day_config = None
            has_shifts = False

        # 计算工作日
        if first_work_day_config:
            # 使用自定义的首个工作日生成工作日列表
            first_day = int(first_work_day_config)
            work_days = generate_work_days_from_first_day(year, month_num, first_day)
        elif has_shifts:
            # 如果有排班数据但没有配置，使用默认锚点逻辑
            work_days = get_work_days_in_month(year, month_num, group_id)
        else:
            # 没有配置也没有数据，返回空工作日列表（等待用户设置）
            work_days = []

        # 获取当前组的员工
        try:
            # 这里的 get_all_employees 返回所有员工，我们需要按组筛选
            # 既然 crud.py 中没有现成的带 filter 的函数，我们直接在这里查询或者在内存中过滤
            # 为了简单可靠，我们使用 SQLAlchemy 直接查询
            employees_db = db.query(EmployeeModel).filter(
                EmployeeModel.group_id == group_id
            ).order_by(EmployeeModel.sequence_order).all()
        except Exception:
            # 数据库失败时返回空列表
            employees_db = []
        employees = [
            EmployeeDTO(
                id=emp.id,
                name=emp.name,
                is_night_leader=emp.is_night_leader,
                sequence_order=emp.sequence_order,
                avoidance_group_id=emp.avoidance_group_id
            )
            for emp in employees_db
        ]

        # 获取避让规则
        try:
            rules_db = get_all_avoidance_rules(db)
        except Exception:
            rules_db = []
        avoidance_rules = [
            AvoidanceRuleDTO(
                id=rule.id,
                name=rule.name,
                member_ids=rule.member_ids_json if rule.member_ids_json else [],
                description=rule.description
            )
            for rule in rules_db
        ]

        # 获取排班记录
        try:
            shifts_db = get_shifts_by_month(db, year, month_num, group_id)
        except Exception:
            shifts_db = []

        # 组织排班数据按日期分组
        schedules_dict = {}
        for shift in shifts_db:
            date_str = shift.date.strftime("%Y-%m-%d")
            if date_str not in schedules_dict:
                schedules_dict[date_str] = {
                    "date": date_str,
                    "day_of_week": get_day_of_week_cn(date_str),
                    "records": []
                }
            schedules_dict[date_str]["records"].append(
                ShiftRecordDTO(
                    employee_id=shift.employee_id,
                    date=date_str,
                    shift_type=shift.shift_type,
                    seat_type=shift.seat_type
                )
            )

        # 为每个工作日创建空结构（如果没有排班数据）
        schedules = []
        for work_day in work_days:
            if work_day in schedules_dict:
                schedules.append(DailyScheduleDTO(**schedules_dict[work_day]))
            else:
                # 创建空排班结构，每个员工都是NONE
                empty_records = [
                    ShiftRecordDTO(
                        employee_id=emp.id,
                        date=work_day,
                        shift_type="NONE",
                        seat_type=None
                    )
                    for emp in employees_db
                ]
                schedules.append(DailyScheduleDTO(
                    date=work_day,
                    day_of_week=get_day_of_week_cn(work_day),
                    records=empty_records
                ))

        return InitDataResponse(
            month=month,
            group_id=group_id,
            work_days=work_days,
            employees=employees,
            schedules=schedules,
            avoidance_rules=avoidance_rules,
            anchor_date=anchor_date,
            anchor_group=anchor_group
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get init data: {str(e)}")


# ============================================
# 新增接口：自动排班（预览，不存库）
# ============================================

@router.post("/schedule/auto-generate", response_model=AutoGenerateResponse)
async def auto_generate_schedule(request: AutoGenerateRequest, db: Session = Depends(get_db)):
    """
    自动生成排班（预览数据，不存库）

    调用 OR-Tools 算法计算排班 -> 不存库，直接返回预览数据给前端

    Args:
        request: 包含月份和组别的请求
        db: 数据库会话

    Returns:
        AutoGenerateResponse: 生成的排班预览数据
    """
    try:
        # 解析月份
        year, month_num = parse_month(request.month)

        # 计算工作日 - 优先使用 system_config 中的自定义首个工作日
        first_work_day_config = get_work_day_config(db, request.month, request.group_id)
        if first_work_day_config:
            first_day = int(first_work_day_config)
            work_days = generate_work_days_from_first_day(year, month_num, first_day)
        else:
            work_days = get_work_days_in_month(year, month_num, request.group_id)

        if not work_days:
            raise HTTPException(
                status_code=400,
                detail=f"No work days found for group {request.group_id} in {request.month}"
            )

        # 如果指定了日期范围，过滤工作日
        if request.start_date and request.end_date:
            work_days = [d for d in work_days if request.start_date <= d <= request.end_date]

        # 获取当前组的员工
        employees_db = db.query(EmployeeModel).filter(
            EmployeeModel.group_id == request.group_id
        ).order_by(EmployeeModel.sequence_order).all()

        if len(employees_db) != 17:
            # 只有当该组实际人数不为17时才报错
            # 但考虑到用户可能正在通过添加按钮逐个添加，这里也许不应该强制报错
            # 不过算法要求17人，所以还是保留检查，但提示更友好
            pass
            raise HTTPException(
                status_code=400,
                detail=f"Expected 17 employees, got {len(employees_db)}"
            )

        # 转换为 Solver 需要的格式
        employees = [
            Employee(
                id=str(emp.id),
                name=emp.name,
                role=EmployeeRole.LEADER if emp.is_night_leader else EmployeeRole.STAFF,
                avoidance_group_id=str(emp.avoidance_group_id) if emp.avoidance_group_id else None
            )
            for emp in employees_db
        ]

        # 获取避让规则
        rules_db = get_all_avoidance_rules(db)
        avoidance_groups = [
            AvoidanceGroup(
                id=str(rule.id),
                employee_ids=[str(eid) for eid in (rule.member_ids_json or [])]
            )
            for rule in rules_db
        ]

        constraints = ScheduleConstraints(avoidance_groups=avoidance_groups)

        # 处理锁定的单元格
        locked_assignments = {}
        if request.locked_records:
            for locked in request.locked_records:
                emp_id = str(locked.get('employee_id'))
                date = locked.get('date')
                shift_type_str = locked.get('shift_type')
                if emp_id and date and shift_type_str:
                    try:
                        shift_type = ShiftType(shift_type_str)
                        locked_assignments[(emp_id, date)] = shift_type
                    except ValueError:
                        # 忽略无效的班次类型
                        pass

        # 获取上个月的最后几天排班数据（用于考虑跨月大夜班间隔）
        from datetime import datetime, timedelta
        from app.services.crud import get_shifts_by_month

        previous_schedules = []
        try:
            # 计算上个月
            first_day_of_month = datetime(year, month_num, 1)
            last_day_prev_month = first_day_of_month - timedelta(days=1)
            prev_year = last_day_prev_month.year
            prev_month = last_day_prev_month.month

            # 获取上个月的排班记录
            prev_shifts = get_shifts_by_month(db, prev_year, prev_month, request.group_id)

            # 按日期分组，只取最后10天
            from collections import defaultdict
            records_by_date = defaultdict(list)
            for shift in prev_shifts:
                records_by_date[shift.shift_date.strftime("%Y-%m-%d")].append(shift)

            sorted_dates = sorted(records_by_date.keys())
            last_10_dates = sorted_dates[-10:] if len(sorted_dates) > 10 else sorted_dates

            # 转换为 DailySchedule 格式
            from app.models.schemas import DailySchedule, ShiftRecord
            for date_str in last_10_dates:
                day_shifts = records_by_date[date_str]
                schedule = DailySchedule(
                    date=date_str,
                    day_of_week="",  # 不需要星期几
                    records=[
                        ShiftRecord(
                            employee_id=str(shift.employee_id),
                            date=date_str,
                            shift_type=ShiftType(shift.shift_type),
                            slot_type=None
                        )
                        for shift in day_shifts
                    ]
                )
                previous_schedules.append(schedule)
        except Exception as e:
            # 上个月数据获取失败不影响本月排班，只是没有历史约束
            print(f"Warning: Failed to get previous month schedules: {e}")
            previous_schedules = []

        # 创建求解器并生成排班
        solver = SchedulingSolver(
            employees=employees,
            work_days=work_days,
            constraints=constraints,
            previous_schedules=previous_schedules,
            locked_assignments=locked_assignments  # 传递锁定的单元格
        )

        schedules_raw, statistics = solver.solve()

        # 转换为 DTO 格式
        schedules = []
        for schedule in schedules_raw:
            records = [
                ShiftRecordDTO(
                    employee_id=int(rec.employee_id),
                    date=rec.date,
                    shift_type=rec.shift_type.value if hasattr(rec.shift_type, 'value') else rec.shift_type,
                    seat_type=rec.slot_type.value if rec.slot_type and hasattr(rec.slot_type, 'value') else rec.slot_type
                )
                for rec in schedule.records
            ]
            schedules.append(DailyScheduleDTO(
                date=schedule.date,
                day_of_week=schedule.day_of_week,
                records=records
            ))

        return AutoGenerateResponse(
            month=request.month,
            group_id=request.group_id,
            work_days=work_days,
            schedules=schedules,
            statistics=statistics
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auto generate failed: {str(e)}")


# ============================================
# 新增接口：保存排班
# ============================================

@router.post("/schedule/save", response_model=SaveScheduleResponse)
async def save_schedule(request: SaveScheduleRequest, db: Session = Depends(get_db)):
    """
    保存排班数据

    开启事务 -> 清除该日期范围旧数据 -> 批量插入新数据 -> 提交

    Args:
        request: 包含排班数据的请求
        db: 数据库会话

    Returns:
        SaveScheduleResponse: 保存结果
    """
    try:
        # 准备排班数据
        schedules_data = []
        for schedule in request.schedules:
            for record in schedule.records:
                # 跳过 NONE 类型的记录
                if record.shift_type == "NONE":
                    continue
                schedules_data.append({
                    "date": record.date,
                    "employee_id": record.employee_id,
                    "shift_type": record.shift_type,
                    "seat_type": record.seat_type
                })

        # 保存到数据库
        saved_count = save_schedules(db, schedules_data, request.group_id)

        return SaveScheduleResponse(
            success=True,
            message=f"Successfully saved {saved_count} shift records",
            saved_count=saved_count
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Save failed: {str(e)}")


@router.put("/schedule/shift", response_model=UpdateShiftResponse)
async def update_shift(request: UpdateShiftRequest, db: Session = Depends(get_db)):
    """
    更新单个班次记录（实时保存）

    Args:
        request: 包含员工ID、日期、班次类型等信息
        db: 数据库会话

    Returns:
        UpdateShiftResponse: 更新结果
    """
    try:
        success = update_single_shift(
            db=db,
            employee_id=request.employee_id,
            shift_date=request.date,
            shift_type=request.shift_type,
            group_id=request.group_id,
            seat_type=request.seat_type
        )

        return UpdateShiftResponse(
            success=success,
            message="Shift updated successfully" if success else "Failed to update shift"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")


# ============================================
# 员工管理接口
# ============================================

@router.get("/employees", response_model=list[EmployeeDTO])
async def get_employees(db: Session = Depends(get_db)):
    """获取所有员工列表"""
    employees_db = get_all_employees(db)
    return [
        EmployeeDTO(
            id=emp.id,
            name=emp.name,
            is_night_leader=emp.is_night_leader,
            sequence_order=emp.sequence_order,
            avoidance_group_id=emp.avoidance_group_id
        )
        for emp in employees_db
    ]


@router.post("/employees", response_model=EmployeeDTO)
async def create_new_employee(request: EmployeeCreateRequest, db: Session = Depends(get_db)):
    """创建新员工"""
    try:
        # 如果没有指定 sequence_order，取最大值+1
        if request.sequence_order is None:
            employees = get_all_employees(db)
            max_order = max([e.sequence_order for e in employees], default=0)
            request.sequence_order = max_order + 1

        emp = create_employee(
            db,
            name=request.name,
            group_id=request.group_id,  # 新增：传递组别参数
            is_night_leader=request.is_night_leader,
            sequence_order=request.sequence_order,
            avoidance_group_id=request.avoidance_group_id
        )

        return EmployeeDTO(
            id=emp.id,
            name=emp.name,
            is_night_leader=emp.is_night_leader,
            sequence_order=emp.sequence_order,
            avoidance_group_id=emp.avoidance_group_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Create employee failed: {str(e)}")


@router.put("/employees/{employee_id}", response_model=EmployeeDTO)
async def update_existing_employee(employee_id: int, request: EmployeeUpdateRequest, db: Session = Depends(get_db)):
    """更新员工信息"""
    try:
        update_data = {k: v for k, v in request.model_dump().items() if v is not None}
        emp = update_employee(db, employee_id, **update_data)

        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")

        return EmployeeDTO(
            id=emp.id,
            name=emp.name,
            is_night_leader=emp.is_night_leader,
            sequence_order=emp.sequence_order,
            avoidance_group_id=emp.avoidance_group_id
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update employee failed: {str(e)}")


@router.delete("/employees/{employee_id}")
async def delete_existing_employee(employee_id: int, db: Session = Depends(get_db)):
    """删除员工"""
    try:
        success = delete_employee(db, employee_id)
        if not success:
            raise HTTPException(status_code=404, detail="Employee not found")
        return {"success": True, "message": "Employee deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete employee failed: {str(e)}")


@router.post("/schedule/validate-day")
async def validate_day_schedule(
    date: str,
    records: List[ShiftRecordDTO],
    db: Session = Depends(get_db)
):
    """
    验证单日排班是否符合规则（A和B规则）

    Args:
        date: 日期字符串 "YYYY-MM-DD"
        records: 排班记录列表
        db: 数据库会话

    Returns:
        验证结果和错误列表
    """
    try:
        from app.services.validator import validate_daily_schedule

        # 获取员工数据
        employees_db = get_all_employees(db)
        employees = [
            Employee(
                id=str(emp.id),
                name=emp.name,
                role=EmployeeRole.LEADER if emp.is_night_leader else EmployeeRole.STAFF,
                avoidance_group_id=str(emp.avoidance_group_id) if emp.avoidance_group_id else None
            )
            for emp in employees_db
        ]

        # 获取避让规则
        rules_db = get_all_avoidance_rules(db)
        avoidance_groups = [
            AvoidanceGroup(
                id=str(rule.id),
                employee_ids=[str(eid) for eid in (rule.member_ids_json or [])]
            )
            for rule in rules_db
        ]

        constraints = ScheduleConstraints(avoidance_groups=avoidance_groups)

        # 转换记录
        shift_records = [
            ShiftRecord(
                employee_id=str(r.employee_id),
                date=r.date,
                shift_type=ShiftType(r.shift_type)
            )
            for r in records
        ]

        # 验证
        errors = validate_daily_schedule(date, shift_records, employees, constraints)

        return {
            "is_valid": len(errors) == 0,
            "errors": [
                {
                    "type": e.error_type,
                    "date": e.date,
                    "message": e.message,
                    "employee_ids": e.employee_ids
                }
                for e in errors
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@router.post("/schedule/validate-month")
async def validate_month_schedule_endpoint(
    schedules: List[DailyScheduleDTO],
    db: Session = Depends(get_db)
):
    """
    验证整月排班（包括公平性检查 - C规则）

    Args:
        schedules: 整月排班数据
        db: 数据库会话

    Returns:
        验证结果和错误列表
    """
    try:
        from app.services.validator import validate_month_schedule

        # 获取员工数据
        employees_db = get_all_employees(db)
        employees = [
            Employee(
                id=str(emp.id),
                name=emp.name,
                role=EmployeeRole.LEADER if emp.is_night_leader else EmployeeRole.STAFF,
                avoidance_group_id=str(emp.avoidance_group_id) if emp.avoidance_group_id else None
            )
            for emp in employees_db
        ]

        # 获取避让规则
        rules_db = get_all_avoidance_rules(db)
        avoidance_groups = [
            AvoidanceGroup(
                id=str(rule.id),
                employee_ids=[str(eid) for eid in (rule.member_ids_json or [])]
            )
            for rule in rules_db
        ]

        constraints = ScheduleConstraints(avoidance_groups=avoidance_groups)

        # 转换为字典格式
        schedules_dict = [
            {
                "date": s.date,
                "records": [
                    {
                        "employee_id": r.employee_id,
                        "date": r.date,
                        "shift_type": r.shift_type
                    }
                    for r in s.records
                ]
            }
            for s in schedules
        ]

        # 验证
        errors = validate_month_schedule(schedules_dict, employees, constraints)

        return {
            "is_valid": len(errors) == 0,
            "errors": [
                {
                    "type": e.error_type,
                    "date": e.date,
                    "message": e.message,
                    "employee_ids": e.employee_ids
                }
                for e in errors
            ],
            "summary": {
                "total_errors": len(errors),
                "error_types": list(set(e.error_type for e in errors))
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


# ============================================
# 工作日配置接口
# ============================================

@router.post("/workday/set-first-day", response_model=SetFirstWorkDayResponse)
async def set_first_work_day(request: SetFirstWorkDayRequest, db: Session = Depends(get_db)):
    """
    设置某月某组的首个工作日，并生成整月工作日列表

    Args:
        request: 包含月份、组别、首个工作日的请求
        db: 数据库会话

    Returns:
        SetFirstWorkDayResponse: 包含生成的工作日列表
    """
    try:
        # 解析月份
        year, month_num = parse_month(request.month)

        # 验证日期有效性
        from calendar import monthrange
        _, days_in_month = monthrange(year, month_num)
        if request.first_work_day > days_in_month:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid day {request.first_work_day} for {request.month}"
            )

        # 保存配置
        config_key = set_work_day_config(db, request.month, request.group_id, request.first_work_day)

        # 生成工作日列表
        work_days = generate_work_days_from_first_day(year, month_num, request.first_work_day)

        return SetFirstWorkDayResponse(
            success=True,
            message=f"成功设置 {request.month} {request.group_id}组首个工作日为 {request.first_work_day} 日",
            work_days=work_days,
            config_key=config_key
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Set first work day failed: {str(e)}")


# ============================================
# 原有接口（保留并优化）
# ============================================

@router.post("/schedule/generate", response_model=GenerateScheduleResponse)
async def generate_schedule(request: GenerateScheduleRequest, db: Session = Depends(get_db)):
    """Generate an optimized schedule for the specified month and group.

    This endpoint uses constraint programming (OR-Tools CP-SAT) to generate
    a schedule that:
    - Assigns exactly 17 people to 17 slots each work day
    - Ensures chief positions are filled by qualified leaders
    - Minimizes late night shift variance across employees
    - Penalizes avoidance group conflicts

    Args:
        request: Schedule generation parameters including month, group,
                 employees, and constraints

    Returns:
        Generated schedule with statistics
    """
    try:
        # Parse month and calculate work days
        year, month = parse_month(request.month)
        first_work_day_config = get_work_day_config(db, request.month, request.group_id)
        if first_work_day_config:
            first_day = int(first_work_day_config)
            work_days = generate_work_days_from_first_day(year, month, first_day)
        else:
            work_days = get_work_days_in_month(year, month, request.group_id)

        if not work_days:
            raise HTTPException(
                status_code=400,
                detail=f"No work days found for group {request.group_id} in {request.month}",
            )

        if len(request.employees) != 17:
            raise HTTPException(
                status_code=400,
                detail=f"Expected 17 employees, got {len(request.employees)}",
            )

        # Create solver and generate schedule
        solver = SchedulingSolver(
            employees=request.employees,
            work_days=work_days,
            constraints=request.constraints,
        )

        schedules, statistics = solver.solve()

        return GenerateScheduleResponse(
            month=request.month,
            group_id=request.group_id,
            work_days=work_days,
            schedules=schedules,
            statistics=statistics,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Schedule generation failed: {str(e)}")


@router.post("/schedule/validate", response_model=ValidateScheduleResponse)
async def validate_schedule(request: ValidateScheduleRequest):
    """Validate a single day's schedule.

    Checks:
    - Total headcount is 17
    - Each shift type has correct number of people
    - Chief positions are filled by qualified leaders
    - No avoidance group conflicts

    Args:
        request: Validation request with date, records, employees, and constraints

    Returns:
        Validation result with any errors found
    """
    errors = validate_daily_schedule(
        date=request.date,
        records=request.records,
        employees=request.employees,
        constraints=request.constraints,
    )

    return ValidateScheduleResponse(
        is_valid=len(errors) == 0,
        errors=errors,
    )


@router.post("/schedule/export")
async def export_schedule(request: ExportScheduleRequest):
    """Export schedule to Excel file.

    Generates a formatted Excel file with:
    - Main sheet: Daily schedule matrix with color-coded shifts
    - Summary sheet: Statistics per employee

    Args:
        request: Export request with month, group, schedules, and employees

    Returns:
        Excel file as streaming response
    """
    try:
        buffer = export_schedule_to_excel(
            month=request.month,
            group_id=request.group_id,
            schedules=request.schedules,
            employees=request.employees,
        )

        filename = f"schedule_{request.month}_{request.group_id}.xlsx"

        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/schedule/workdays/{month}/{group_id}")
async def get_work_days(month: str, group_id: str, db: Session = Depends(get_db)):
    """Get work days for a specific month and group.

    Uses the anchor logic where 2024-01-01 is Group A's work day,
    and groups rotate on a 3-day cycle.

    Args:
        month: Month in YYYY-MM format
        group_id: Group identifier (A, B, or C)

    Returns:
        List of work day dates
    """
    try:
        year, month_num = parse_month(month)
        first_work_day_config = get_work_day_config(db, month, group_id)
        if first_work_day_config:
            first_day = int(first_work_day_config)
            work_days = generate_work_days_from_first_day(year, month_num, first_day)
        else:
            work_days = get_work_days_in_month(year, month_num, group_id)

        return {
            "month": month,
            "group_id": group_id,
            "work_days": work_days,
            "count": len(work_days),
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================
# 新增：GET /api/export 导出Excel
# ============================================

@router.get("/export")
async def export_schedule_get(month: str, group_id: str, db: Session = Depends(get_db)):
    """
    导出排班表到 Excel 文件（GET 方式）

    从数据库读取排班数据并生成 Excel 文件流

    Args:
        month: 月份，格式 YYYY-MM
        group_id: 组别 A/B/C
        db: 数据库会话

    Returns:
        Excel 文件流
    """
    try:
        # 解析月份
        year, month_num = parse_month(month)

        # 获取当前组的员工
        employees_db = db.query(EmployeeModel).filter(
            EmployeeModel.group_id == group_id
        ).order_by(EmployeeModel.sequence_order).all()
        employees = [
            Employee(
                id=str(emp.id),
                name=emp.name,
                role=EmployeeRole.LEADER if emp.is_night_leader else EmployeeRole.STAFF,
                avoidance_group_id=str(emp.avoidance_group_id) if emp.avoidance_group_id else None
            )
            for emp in employees_db
        ]

        # 获取排班数据
        shifts_db = get_shifts_by_month(db, year, month_num, group_id)

        # 组织排班数据
        first_work_day_config = get_work_day_config(db, month, group_id)
        if first_work_day_config:
            first_day = int(first_work_day_config)
            work_days = generate_work_days_from_first_day(year, month_num, first_day)
        else:
            work_days = get_work_days_in_month(year, month_num, group_id)
        schedules_dict = {}

        for shift in shifts_db:
            date_str = shift.date.strftime("%Y-%m-%d")
            if date_str not in schedules_dict:
                schedules_dict[date_str] = {
                    "date": date_str,
                    "day_of_week": get_day_of_week_cn(date_str),
                    "records": []
                }
            schedules_dict[date_str]["records"].append(
                ShiftRecord(
                    employee_id=str(shift.employee_id),
                    date=date_str,
                    shift_type=shift.shift_type,
                    slot_type=shift.seat_type
                )
            )

        # 构建完整的排班列表
        schedules = []
        for work_day in work_days:
            if work_day in schedules_dict:
                data = schedules_dict[work_day]
                schedules.append(DailySchedule(
                    date=data["date"],
                    day_of_week=data["day_of_week"],
                    records=data["records"]
                ))
            else:
                # 空排班
                schedules.append(DailySchedule(
                    date=work_day,
                    day_of_week=get_day_of_week_cn(work_day),
                    records=[]
                ))

        # 生成 Excel
        buffer = export_schedule_to_excel(
            month=month,
            group_id=group_id,
            schedules=schedules,
            employees=employees
        )

        filename = f"schedule_{month}_{group_id}.xlsx"

        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
