"""
测试调度求解器 - 验证大夜班最大间隔约束
"""
from app.services.scheduler import SchedulingSolver
from app.models.schemas import Employee, EmployeeRole, ScheduleConstraints, ShiftType
from datetime import datetime, timedelta

# 创建17个员工（6个主任 + 11个普通员工）
employees = []
for i in range(17):
    emp = Employee(
        id=str(i+1),
        name=f"员工{i+1}",
        role=EmployeeRole.LEADER if i < 6 else EmployeeRole.STAFF,
        avoidance_group_id=None
    )
    employees.append(emp)

# 生成工作日：每3天一次（模拟真实排班）
start_date = datetime(2026, 3, 2)  # A组3月首个工作日
work_days = []
current = start_date
end_date = datetime(2026, 3, 31)
while current <= end_date:
    work_days.append(current.strftime("%Y-%m-%d"))
    current += timedelta(days=3)

print(f"Work days ({len(work_days)}): {work_days}")

# 空约束
constraints = ScheduleConstraints(avoidance_groups=[])


def check_late_night_gaps(schedules, employees):
    """检查每个员工的大夜班间隔"""
    print("\n--- 大夜班间隔检查 ---")
    all_ok = True

    for emp in employees:
        if emp.id == "1":  # 跳过第一人
            continue

        is_leader = emp.role == EmployeeRole.LEADER
        max_gap = 5 if is_leader else 6

        # 收集该员工所有大夜班日期
        late_night_days = []
        for schedule in sorted(schedules, key=lambda s: s.date):
            for record in schedule.records:
                if record.employee_id == emp.id and record.shift_type == ShiftType.LATE_NIGHT:
                    late_night_days.append(schedule.date)
                    break

        # 检查间隔
        if len(late_night_days) == 0:
            print(f"  FAIL {emp.name} ({'主任' if is_leader else '普通'}): 无大夜班!")
            all_ok = False
            continue

        # 检查从月初到第一个大夜班的间距（用工作日索引）
        work_day_indices = {d: i for i, d in enumerate(work_days)}
        first_ln_idx = work_day_indices[late_night_days[0]]
        if first_ln_idx > max_gap:
            print(f"  FAIL {emp.name}: 月初到首个大夜班间隔 {first_ln_idx} 个工作日 > max_gap={max_gap}")
            all_ok = False

        # 检查相邻大夜班之间的间隔
        for i in range(len(late_night_days) - 1):
            idx1 = work_day_indices[late_night_days[i]]
            idx2 = work_day_indices[late_night_days[i+1]]
            gap = idx2 - idx1 - 1  # 中间隔了几个工作日
            if gap > max_gap:
                print(f"  FAIL {emp.name}: {late_night_days[i]} -> {late_night_days[i+1]} 间隔 {gap} 个工作日 > max_gap={max_gap}")
                all_ok = False

        # 检查最后一个大夜班到月末
        last_ln_idx = work_day_indices[late_night_days[-1]]
        tail_gap = len(work_days) - 1 - last_ln_idx
        # 月末间隔不是硬性要求（下个月会桥接），但打印出来供参考

        if all_ok or emp.id in ["16", "17"]:  # 始终打印最后几个员工的情况
            print(f"  OK {emp.name} ({'主任' if is_leader else '普通'}): "
                  f"{len(late_night_days)}次大夜 @ {late_night_days}, "
                  f"尾部间隔={tail_gap}")

    return all_ok


def check_shifts_per_day(schedules):
    """检查每天的人数分配是否正确"""
    print("\n--- 每日班次人数检查 ---")
    all_ok = True
    for schedule in sorted(schedules, key=lambda s: s.date):
        counts = {}
        for record in schedule.records:
            st = record.shift_type.value
            counts[st] = counts.get(st, 0) + 1
        expected = {"DAY": 6, "SLEEP": 5, "MINI_NIGHT": 3, "LATE_NIGHT": 3}
        if counts != expected:
            print(f"  FAIL {schedule.date}: {counts} (expected {expected})")
            all_ok = False
    if all_ok:
        print(f"  OK 所有 {len(schedules)} 天人数分配正确")
    return all_ok


# ============================
# Test 1: 无历史数据
# ============================
print("=" * 60)
print("=== Test 1: 无历史数据，10个工作日 ===")
print("=" * 60)
try:
    solver = SchedulingSolver(
        employees=employees,
        work_days=work_days,
        constraints=constraints,
        previous_schedules=None,
        locked_assignments={}
    )
    schedules, stats = solver.solve()
    print(f"求解成功! 生成 {len(schedules)} 天排班")

    check_shifts_per_day(schedules)
    ok = check_late_night_gaps(schedules, employees)
    print(f"\n大夜班最大间隔检查: {'PASS' if ok else 'FAIL'}")

    # 检查第一个员工的规律
    first_emp_shifts = []
    for schedule in sorted(schedules, key=lambda s: s.date):
        for record in schedule.records:
            if record.employee_id == "1":
                first_emp_shifts.append(record.shift_type.value)
                break
    print(f"\n第一个员工班次: {' '.join(first_emp_shifts)}")

except Exception as e:
    print(f"FAIL: {e}")
    import traceback
    traceback.print_exc()


# ============================
# Test 2: 有上月历史数据（模拟跨月）
# ============================
print("\n" + "=" * 60)
print("=== Test 2: 有上月历史数据（跨月桥接测试） ===")
print("=" * 60)
try:
    from app.models.schemas import DailySchedule, ShiftRecord

    # 模拟上月最后几天的排班数据
    # 所有员工最后一次大夜班在2月中旬（距3月较远，考验桥接约束）
    prev_schedules = []
    prev_date = "2026-02-15"
    prev_records = []
    for i, emp in enumerate(employees):
        if i == 0:
            shift = ShiftType.SLEEP
        elif i < 3:
            shift = ShiftType.LATE_NIGHT
        elif i < 6:
            shift = ShiftType.DAY
        elif i < 9:
            shift = ShiftType.LATE_NIGHT  # 这些普通员工上月15日有大夜
        else:
            shift = ShiftType.SLEEP
        prev_records.append(ShiftRecord(
            employee_id=emp.id, date=prev_date,
            shift_type=shift, slot_type=None
        ))
    prev_schedules.append(DailySchedule(
        date=prev_date, day_of_week="周日", records=prev_records
    ))

    # 添加上月最后一天的数据
    prev_date2 = "2026-02-27"
    prev_records2 = []
    for i, emp in enumerate(employees):
        if i == 0:
            shift = ShiftType.DAY
        elif i < 3:
            shift = ShiftType.DAY
        elif i < 6:
            shift = ShiftType.SLEEP
        elif i < 9:
            shift = ShiftType.SLEEP
        else:
            shift = ShiftType.DAY
        prev_records2.append(ShiftRecord(
            employee_id=emp.id, date=prev_date2,
            shift_type=shift, slot_type=None
        ))
    prev_schedules.append(DailySchedule(
        date=prev_date2, day_of_week="周五", records=prev_records2
    ))

    solver = SchedulingSolver(
        employees=employees,
        work_days=work_days,
        constraints=constraints,
        previous_schedules=prev_schedules,
        locked_assignments={}
    )
    schedules, stats = solver.solve()
    print(f"求解成功! 生成 {len(schedules)} 天排班")

    check_shifts_per_day(schedules)
    ok = check_late_night_gaps(schedules, employees)
    print(f"\n大夜班最大间隔检查: {'PASS' if ok else 'FAIL'}")

except Exception as e:
    print(f"FAIL: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
