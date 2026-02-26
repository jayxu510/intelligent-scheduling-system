"""Validation service for schedule data."""

from collections import defaultdict, Counter
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

from app.models.schemas import (
    Employee,
    EmployeeRole,
    ShiftType,
    ShiftRecord,
    ScheduleConstraints,
    ValidationError,
)


# Expected counts per shift type
SHIFT_REQUIREMENTS = {
    ShiftType.DAY: 6,
    ShiftType.SLEEP: 5,
    ShiftType.MINI_NIGHT: 3,
    ShiftType.LATE_NIGHT: 3,
}

TOTAL_REQUIRED = 17

# Shifts that require a chief (leader)
CHIEF_REQUIRED_SHIFTS = [ShiftType.SLEEP, ShiftType.MINI_NIGHT, ShiftType.LATE_NIGHT]


def validate_daily_schedule(
    date: str,
    records: list[ShiftRecord],
    employees: list[Employee],
    constraints: ScheduleConstraints,
) -> list[ValidationError]:
    """Validate a single day's schedule.

    Checks:
    1. Total personnel count is 17
    2. Each shift type has correct number of people
    3. Chief positions are filled by leaders
    4. Avoidance group conflicts

    Args:
        date: The date being validated
        records: List of shift records for the day
        employees: List of all employees
        constraints: Scheduling constraints including avoidance groups

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    emp_by_id = {e.id: e for e in employees}
    leader_ids = {e.id for e in employees if e.role == EmployeeRole.LEADER}

    # Filter out NONE and VACATION shifts for counting
    active_records = [r for r in records if r.shift_type not in [ShiftType.NONE, ShiftType.VACATION]]

    # Check 1: Total personnel count
    if len(active_records) != TOTAL_REQUIRED:
        errors.append(
            ValidationError(
                error_type="HEADCOUNT_MISMATCH",
                date=date,
                message=f"定员不足: 需要{TOTAL_REQUIRED}人，实际{len(active_records)}人",
                employee_ids=[],
            )
        )

    # Check 2: Shift type counts
    shift_counts = defaultdict(int)
    shift_employees: dict[ShiftType, list[str]] = defaultdict(list)

    for record in active_records:
        shift_counts[record.shift_type] += 1
        shift_employees[record.shift_type].append(record.employee_id)

    for shift_type, required in SHIFT_REQUIREMENTS.items():
        actual = shift_counts[shift_type]
        if actual != required:
            shift_name = _get_shift_name(shift_type)
            errors.append(
                ValidationError(
                    error_type="SHIFT_COUNT_MISMATCH",
                    date=date,
                    message=f"{shift_name}人数错误: 需要{required}人，实际{actual}人",
                    employee_ids=shift_employees[shift_type],
                )
            )

    # Check 3: Chief positions must be filled by leaders
    for shift_type in CHIEF_REQUIRED_SHIFTS:
        emps_in_shift = shift_employees[shift_type]
        leaders_in_shift = [e for e in emps_in_shift if e in leader_ids]

        if len(leaders_in_shift) == 0:
            shift_name = _get_shift_name(shift_type)
            errors.append(
                ValidationError(
                    error_type="CHIEF_MISSING",
                    date=date,
                    message=f"{shift_name}缺少主任席（夜班长）",
                    employee_ids=emps_in_shift,
                )
            )
        elif len(leaders_in_shift) > 1:
            shift_name = _get_shift_name(shift_type)
            errors.append(
                ValidationError(
                    error_type="CHIEF_DUPLICATE",
                    date=date,
                    message=f"{shift_name}存在多个主任席（夜班长）",
                    employee_ids=leaders_in_shift,
                )
            )

    # Check 4: Avoidance group conflicts
    for group in constraints.avoidance_groups:
        group_emp_ids = set(group.employee_ids)

        for shift_type, emps_in_shift in shift_employees.items():
            conflicting = [e for e in emps_in_shift if e in group_emp_ids]
            if len(conflicting) > 1:
                shift_name = _get_shift_name(shift_type)
                emp_names = [emp_by_id[e].name for e in conflicting if e in emp_by_id]
                errors.append(
                    ValidationError(
                        error_type="AVOIDANCE_CONFLICT",
                        date=date,
                        message=f"{shift_name}存在避让冲突: {', '.join(emp_names)}",
                        employee_ids=conflicting,
                    )
                )

    # Check 5: Duplicate employee assignments
    seen_employees = set()
    duplicates = []
    for record in records:
        if record.shift_type not in [ShiftType.NONE, ShiftType.VACATION]:
            if record.employee_id in seen_employees:
                duplicates.append(record.employee_id)
            seen_employees.add(record.employee_id)

    if duplicates:
        dup_names = [emp_by_id[e].name for e in duplicates if e in emp_by_id]
        errors.append(
            ValidationError(
                error_type="DUPLICATE_ASSIGNMENT",
                date=date,
                message=f"员工重复分配: {', '.join(dup_names)}",
                employee_ids=duplicates,
            )
        )

    return errors


def validate_month_schedule(
    schedules: List[Dict],
    employees: list[Employee],
    constraints: ScheduleConstraints,
) -> list[ValidationError]:
    """
    验证整月排班，包括公平性检查（C规则）

    Args:
        schedules: 整月排班数据 [{"date": "2024-01-01", "records": [...]}, ...]
        employees: 员工列表
        constraints: 约束条件

    Returns:
        错误列表
    """
    errors = []
    emp_by_id = {e.id: e for e in employees}

    # 先验证每日排班
    for schedule in schedules:
        date_str = schedule['date']
        records = [ShiftRecord(**r) for r in schedule['records']]
        daily_errors = validate_daily_schedule(date_str, records, employees, constraints)
        errors.extend(daily_errors)

    # C规则：公平性检查
    fairness_errors = _check_fairness(schedules, employees)
    errors.extend(fairness_errors)

    # C规则：连续夜班检查
    consecutive_errors = _check_consecutive_nights(schedules, employees)
    errors.extend(consecutive_errors)

    return errors


def _check_fairness(schedules: List[Dict], employees: list[Employee]) -> list[ValidationError]:
    """
    检查大夜班分配公平性（C规则）
    确保每人的大夜班总数标准差最小
    """
    errors = []
    emp_by_id = {e.id: e for e in employees}

    # 统计每人的大夜班次数
    late_night_counts = defaultdict(int)

    for schedule in schedules:
        for record in schedule['records']:
            if record.get('shift_type') == 'LATE_NIGHT':
                late_night_counts[record['employee_id']] += 1

    if not late_night_counts:
        return errors

    # 计算标准差
    counts = list(late_night_counts.values())
    mean = sum(counts) / len(counts)
    variance = sum((x - mean) ** 2 for x in counts) / len(counts)
    std_dev = variance ** 0.5

    # 标准差阈值：2.0
    if std_dev > 2.0:
        # 找出大夜班次数最多和最少的员工
        max_count = max(counts)
        min_count = min(counts)
        max_emps = [eid for eid, cnt in late_night_counts.items() if cnt == max_count]
        min_emps = [eid for eid, cnt in late_night_counts.items() if cnt == min_count]

        max_names = [emp_by_id[e].name for e in max_emps if e in emp_by_id]
        min_names = [emp_by_id[e].name for e in min_emps if e in emp_by_id]

        errors.append(
            ValidationError(
                error_type="FAIRNESS_IMBALANCE",
                date="",
                message=f"大夜班分配不均衡（标准差: {std_dev:.2f}）。最多: {', '.join(max_names)}({max_count}次)；最少: {', '.join(min_names)}({min_count}次)",
                employee_ids=max_emps + min_emps,
            )
        )

    return errors


def _check_consecutive_nights(schedules: List[Dict], employees: list[Employee]) -> list[ValidationError]:
    """
    检查连续班次违规（C规则）
    所有班次类型都不应该连续出现（相邻工作日同一人同一班次）。
    """
    errors = []
    emp_by_id = {e.id: e for e in employees}

    SHIFT_NAMES = {
        'DAY': '白班',
        'SLEEP': '睡觉班',
        'MINI_NIGHT': '小夜班',
        'LATE_NIGHT': '大夜班',
    }

    # 按员工分组，记录每人每天的班次
    employee_shifts: Dict[str, list] = defaultdict(list)

    for schedule in schedules:
        date_str = schedule['date']
        for record in schedule['records']:
            shift_type = record.get('shift_type')
            if shift_type and shift_type != 'NONE' and shift_type != 'VACATION':
                employee_shifts[record['employee_id']].append({
                    'date': date_str,
                    'shift_type': shift_type
                })

    for emp_id, shifts in employee_shifts.items():
        if len(shifts) < 2:
            continue

        shifts.sort(key=lambda x: x['date'])
        emp_name = emp_by_id[emp_id].name if emp_id in emp_by_id else str(emp_id)

        # 检查相邻工作日是否有同一班次连续
        for i in range(len(shifts) - 1):
            current = shifts[i]
            next_s = shifts[i + 1]

            if current['shift_type'] == next_s['shift_type']:
                shift_name = SHIFT_NAMES.get(current['shift_type'], current['shift_type'])
                errors.append(
                    ValidationError(
                        error_type="CONSECUTIVE_SHIFT",
                        date=current['date'],
                        message=f"{emp_name} 在 {current['date']} 和 {next_s['date']} 连续上{shift_name}",
                        employee_ids=[emp_id],
                    )
                )

    return errors


def _get_shift_name(shift_type: ShiftType) -> str:
    """Get Chinese name for shift type."""
    names = {
        ShiftType.DAY: "白班",
        ShiftType.SLEEP: "睡觉班",
        ShiftType.MINI_NIGHT: "小夜班",
        ShiftType.LATE_NIGHT: "大夜班",
        ShiftType.VACATION: "休假",
        ShiftType.NONE: "无",
    }
    return names.get(shift_type, shift_type.value)
