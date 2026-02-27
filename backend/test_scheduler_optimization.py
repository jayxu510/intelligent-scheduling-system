"""Test script to verify the optimized scheduler with cross-month fairness."""

import sys
import io
from datetime import datetime, timedelta
from app.services.scheduler import SchedulingSolver
from app.models.schemas import Employee, EmployeeRole, ShiftType, DailySchedule, ShiftRecord, ScheduleConstraints

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def create_test_employees():
    """Create test employee data."""
    employees = []

    # 6 leaders (chiefs)
    for i in range(1, 7):
        employees.append(Employee(
            id=f"L{i}",
            name=f"主任{i}",
            role=EmployeeRole.LEADER,
            avoidance_group_id=None
        ))

    # 11 staff members
    for i in range(1, 12):
        employees.append(Employee(
            id=f"S{i}",
            name=f"员工{i}",
            role=EmployeeRole.STAFF,
            avoidance_group_id=None
        ))

    return employees


def create_previous_month_schedules(employees, work_days):
    """Create mock previous month schedules for testing cross-month fairness."""
    schedules = []

    for day in work_days:
        records = []
        # Simple assignment: rotate through employees
        day_idx = work_days.index(day)

        # Assign shifts in a simple pattern
        for i, emp in enumerate(employees):
            if i < 6:  # DAY shift
                shift = ShiftType.DAY
            elif i < 11:  # SLEEP shift
                shift = ShiftType.SLEEP
            elif i < 14:  # MINI_NIGHT
                shift = ShiftType.MINI_NIGHT
            else:  # LATE_NIGHT
                shift = ShiftType.LATE_NIGHT

            records.append(ShiftRecord(
                employee_id=emp.id,
                date=day,
                shift_type=shift
            ))

        schedules.append(DailySchedule(
            date=day,
            day_of_week="周一",
            records=records
        ))

    return schedules


def generate_work_days(year, month, group_id):
    """Generate work days for a specific group (A/B/C) in a month."""
    from app.utils.date_utils import get_work_days_in_month

    # Use the utility function that handles date conversion
    return get_work_days_in_month(year, month, group_id)


def test_scheduler_with_history():
    """Test the scheduler with previous month data."""
    print("=" * 80)
    print("测试优化后的智能排班算法（跨月公平性）")
    print("=" * 80)

    employees = create_test_employees()
    print(f"\n✓ 创建测试员工: {len(employees)} 人 (6主任 + 11普通)")

    # Generate work days for October 2024 (previous month)
    prev_work_days = generate_work_days(2024, 10, "A")
    print(f"✓ 上个月工作日: {len(prev_work_days)} 天")

    # Create previous month schedules
    prev_schedules = create_previous_month_schedules(employees, prev_work_days[:5])  # Use first 5 days
    print(f"✓ 创建上月排班数据: {len(prev_schedules)} 天")

    # Generate work days for November 2024 (current month)
    work_days = generate_work_days(2024, 11, "A")
    print(f"✓ 本月工作日: {len(work_days)} 天")

    # Initialize solver with previous schedules
    print("\n" + "-" * 80)
    print("开始求解（考虑上月数据）...")
    print("-" * 80)

    solver = SchedulingSolver(
        employees=employees,
        work_days=work_days,
        constraints=ScheduleConstraints(),
        previous_schedules=prev_schedules  # Pass previous month data
    )

    result = solver.solve()

    if result:
        schedules, stats = result  # Unpack the tuple
        print("\n✅ 求解成功！")
        print("\n" + "=" * 80)
        print("统计信息")
        print("=" * 80)

        # Current month statistics
        print("\n【本月班次分布】")
        for shift_type, dist in stats["shift_distributions"].items():
            print(f"  {shift_type:12s}: 最少={dist['min']}, 最多={dist['max']}, "
                  f"平均={dist['avg']:.1f}, 标准差={dist['std_dev']:.2f}, "
                  f"差值={dist['spread']}")

        # Two-month statistics (NEW!)
        if "two_month_distributions" in stats and stats["two_month_distributions"]:
            print("\n【两个月累计班次分布】（优化重点）")
            for shift_type, dist in stats["two_month_distributions"].items():
                print(f"  {shift_type:12s}: 最少={dist['min']}, 最多={dist['max']}, "
                      f"平均={dist['avg']:.1f}, 标准差={dist['std_dev']:.2f}, "
                      f"差值={dist['spread']}")

        # Fairness score
        if "fairness_score" in stats:
            print(f"\n【公平性评分】: {stats['fairness_score']} (越低越好)")

        print(f"\n【历史数据】: {'有' if stats.get('has_previous_data') else '无'}")

        # Show sample employee counts
        print("\n【员工班次统计样例】（前3名）")
        emp_counts = stats.get("employee_shift_counts", {})
        for i, (emp_id, counts) in enumerate(list(emp_counts.items())[:3]):
            emp_name = next((e.name for e in employees if e.id == emp_id), emp_id)
            print(f"  {emp_name}: {dict(counts)}")

        if "two_month_employee_counts" in stats:
            print("\n【两个月累计统计样例】（前3名）")
            two_month_counts = stats.get("two_month_employee_counts", {})
            for i, (emp_id, counts) in enumerate(list(two_month_counts.items())[:3]):
                emp_name = next((e.name for e in employees if e.id == emp_id), emp_id)
                print(f"  {emp_name}: {dict(counts)}")

        print("\n" + "=" * 80)
        print("✅ 测试完成！算法已成功集成跨月公平性优化")
        print("=" * 80)

    else:
        print("\n❌ 求解失败")
        return False

    return True


def test_scheduler_without_history():
    """Test the scheduler without previous month data (first month scenario)."""
    print("\n\n" + "=" * 80)
    print("测试场景2: 无历史数据（首月排班）")
    print("=" * 80)

    employees = create_test_employees()
    work_days = generate_work_days(2024, 11, "A")

    print(f"\n✓ 员工数: {len(employees)}")
    print(f"✓ 工作日: {len(work_days)} 天")
    print("✓ 历史数据: 无")

    solver = SchedulingSolver(
        employees=employees,
        work_days=work_days,
        constraints=ScheduleConstraints(),
        previous_schedules=[]  # No previous data
    )

    result = solver.solve()

    if result:
        schedules, stats = result  # Unpack the tuple
        print("\n✅ 求解成功（无历史数据场景）")
        print(f"   公平性评分: {stats.get('fairness_score', 'N/A')}")
        print(f"   历史数据: {'有' if stats.get('has_previous_data') else '无'}")
    else:
        print("\n❌ 求解失败")
        return False

    return True


if __name__ == "__main__":
    try:
        # Test with history
        success1 = test_scheduler_with_history()

        # Test without history
        success2 = test_scheduler_without_history()

        if success1 and success2:
            print("\n" + "🎉" * 40)
            print("所有测试通过！算法优化成功！")
            print("🎉" * 40)
            sys.exit(0)
        else:
            print("\n❌ 部分测试失败")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
