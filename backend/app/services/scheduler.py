"""Scheduling solver using Google OR-Tools CP-SAT solver.

Algorithm Design (基于 OR-Tools 约束规划的智能排班算法):
=================================================================

This solver implements a constraint satisfaction problem (CSP) using Google's
OR-Tools CP-SAT solver to generate optimal shift schedules that satisfy complex
business rules while maximizing fairness.

Core Approach:
--------------
1. Decision Variables: x[employee, day, shift_type] - boolean assignment variables
2. Hard Constraints: Must be satisfied (headcount, chief requirements, intervals)
3. Soft Constraints: Penalized in objective (consecutive shifts, max gaps)
4. Objective: Minimize weighted sum of penalties + maximize fairness

Key Features:
-------------
1. **Cross-Month Fairness (规则4和6)**:
   - Considers previous month shift counts when optimizing current month
   - Minimizes spread (max-min) of two-month cumulative shift counts
   - Ensures long-term balance across all employees

2. **Interval Constraints (规则2和3)**:
   - Late night shifts: 3-5 day minimum gap (chiefs), 3-6 days (staff)
   - Day shifts: 1-3 day minimum gap (staff only, chiefs have soft constraint)
   - Cross-month validation using previous month's last shift dates

3. **Fixed Pattern for First Employee (规则1)**:
   - Cycles through: 1 day shift → 2 sleep shifts → repeat
   - Hard constraint ensures consistency

4. **Consecutive Shift Avoidance (规则5)**:
   - High penalty (1000x) for any consecutive shifts of same type
   - Solver prioritizes eliminating consecutive assignments

5. **Soft Constraints for Flexibility**:
   - Maximum gap violations are penalized but not forbidden
   - Prevents "no solution" scenarios when constraints conflict
   - Allows graceful degradation under tight resource constraints

Constraint Priority (by weight):
---------------------------------
- Consecutive shifts: 1000 (highest priority to avoid)
- Interval violations: 500 (important but flexible)
- Fairness spread: 200 (balance across employees)
- Random perturbation: 0-3 (tie-breaking for variety)

References:
-----------
Based on recommendations from constraint programming best practices for
shift scheduling with fairness objectives and interval constraints.
"""

from ortools.sat.python import cp_model
from collections import defaultdict
import statistics

from app.models.schemas import (
    Employee,
    EmployeeRole,
    ShiftType,
    SlotType,
    ShiftRecord,
    DailySchedule,
    ScheduleConstraints,
)
from app.utils.date_utils import get_day_of_week_cn


# Slot configuration: shift_type -> list of (slot_type, count, requires_leader)
SLOT_CONFIG = {
    ShiftType.DAY: [
        (SlotType.DAY_REGULAR, 6, False),
    ],
    ShiftType.SLEEP: [
        (SlotType.SLEEP_CHIEF, 1, True),
        (SlotType.SLEEP_NORTHWEST, 2, False),
        (SlotType.SLEEP_SOUTHEAST, 2, False),
    ],
    ShiftType.MINI_NIGHT: [
        (SlotType.MINI_NIGHT_CHIEF, 1, True),
        (SlotType.MINI_NIGHT_REGULAR, 2, False),
    ],
    ShiftType.LATE_NIGHT: [
        (SlotType.LATE_NIGHT_CHIEF, 1, True),
        (SlotType.LATE_NIGHT_REGULAR, 2, False),
    ],
}

# Total slots per shift type
SHIFT_TOTALS = {
    ShiftType.DAY: 6,
    ShiftType.SLEEP: 5,
    ShiftType.MINI_NIGHT: 3,
    ShiftType.LATE_NIGHT: 3,
}

TOTAL_SLOTS = 17  # Must equal sum of SHIFT_TOTALS


class SchedulingSolver:
    """Constraint-based scheduling solver using OR-Tools CP-SAT."""

    def __init__(
        self,
        employees: list[Employee],
        work_days: list[str],
        constraints: ScheduleConstraints,
        previous_schedules: list[DailySchedule] | None = None,
        locked_assignments: dict[tuple[str, str], ShiftType] | None = None,  # 新增：锁定的单元格 {(emp_id, date): shift_type}
    ):
        self.employees = employees
        self.work_days = work_days
        self.constraints = constraints
        self.previous_schedules = previous_schedules or []
        self.locked_assignments = locked_assignments or {}  # 新增

        # Index mappings
        self.emp_ids = [e.id for e in employees]
        self.emp_by_id = {e.id: e for e in employees}
        self.leader_ids = [e.id for e in employees if e.role == EmployeeRole.LEADER]

        # Build avoidance lookup
        self.avoidance_pairs: list[tuple[str, str]] = []
        for group in constraints.avoidance_groups:
            ids = group.employee_ids
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    self.avoidance_pairs.append((ids[i], ids[j]))

        # 构建历史大夜班映射：每个员工最后一次上大夜班的日期
        self.last_late_night: dict[str, str] = {}
        # 构建历史班次统计：每个员工上个月各班次的数量（用于跨月公平性）
        self.prev_shift_counts: dict[str, dict[ShiftType, int]] = defaultdict(lambda: defaultdict(int))

        if self.previous_schedules:
            sorted_prev = sorted(self.previous_schedules, key=lambda s: s.date)
            for schedule in sorted_prev:
                for record in schedule.records:
                    # 记录最后一次大夜班日期
                    if record.shift_type == ShiftType.LATE_NIGHT:
                        self.last_late_night[record.employee_id] = schedule.date
                    # 统计各班次数量（排除NONE和VACATION）
                    if record.shift_type not in [ShiftType.NONE, ShiftType.VACATION]:
                        self.prev_shift_counts[record.employee_id][record.shift_type] += 1

        # --- 新增：计算第一名员工的跨月班次规律 (1白2睡循环) ---
        self.first_emp_offset = 0
        if len(self.emp_ids) > 0:
            first_emp_id = self.emp_ids[0]
            if self.previous_schedules:
                sorted_prev = sorted(self.previous_schedules, key=lambda s: s.date)
                history = []
                for schedule in sorted_prev:
                    for record in schedule.records:
                        if record.employee_id == first_emp_id:
                            history.append(record.shift_type)
                
                # 获取最后两天的排班记录来推导本月第一天的状态
                if len(history) >= 2:
                    last_two = history[-2:]
                    if last_two[1] == ShiftType.DAY:
                        self.first_emp_offset = 1  # 昨白 -> 今睡1
                    elif last_two[0] == ShiftType.DAY and last_two[1] == ShiftType.SLEEP:
                        self.first_emp_offset = 2  # 昨睡1 -> 今睡2
                    elif last_two[0] == ShiftType.SLEEP and last_two[1] == ShiftType.SLEEP:
                        self.first_emp_offset = 0  # 昨睡2 -> 今白
                elif len(history) == 1:
                    if history[0] == ShiftType.DAY:
                        self.first_emp_offset = 1
                    else:
                        self.first_emp_offset = 2                

    def solve(self) -> tuple[list[DailySchedule], dict]:
        """Solve the scheduling problem.

        Returns:
            Tuple of (schedules, statistics)
        """
        model = cp_model.CpModel()

        # Decision variables: x[emp_id, day, shift_type] = 1 if assigned
        x = {}
        shift_types = [ShiftType.DAY, ShiftType.SLEEP, ShiftType.MINI_NIGHT, ShiftType.LATE_NIGHT]

        for emp_id in self.emp_ids:
            for day in self.work_days:
                for shift in shift_types:
                    x[emp_id, day, shift] = model.NewBoolVar(f"x_{emp_id}_{day}_{shift.value}")

        # Chief assignment variables: c[emp_id, day, shift_type] = 1 if assigned as chief
        c = {}
        chief_shifts = [ShiftType.SLEEP, ShiftType.MINI_NIGHT, ShiftType.LATE_NIGHT]
        for emp_id in self.leader_ids:
            for day in self.work_days:
                for shift in chief_shifts:
                    c[emp_id, day, shift] = model.NewBoolVar(f"c_{emp_id}_{day}_{shift.value}")

        # Constraint 1: Each employee works exactly one shift per day
        for emp_id in self.emp_ids:
            for day in self.work_days:
                model.Add(sum(x[emp_id, day, shift] for shift in shift_types) == 1)

        # Constraint 2: Each shift type has exactly the required number of people
        for day in self.work_days:
            for shift, count in SHIFT_TOTALS.items():
                model.Add(sum(x[emp_id, day, shift] for emp_id in self.emp_ids) == count)

        # Constraint 3: Each chief shift has exactly one leader assigned
        for day in self.work_days:
            for shift in chief_shifts:
                model.Add(sum(c[emp_id, day, shift] for emp_id in self.leader_ids) == 1)

        # Constraint 4: Chief assignment implies shift assignment
        for emp_id in self.leader_ids:
            for day in self.work_days:
                for shift in chief_shifts:
                    model.Add(c[emp_id, day, shift] <= x[emp_id, day, shift])

        # Constraint 5: A leader can be chief for at most one shift per day
        for emp_id in self.leader_ids:
            for day in self.work_days:
                model.Add(sum(c[emp_id, day, shift] for shift in chief_shifts) <= 1)

        # Constraint 6: Exactly 1 leader per night shift type per day
        # This prevents multiple leaders from being in the same night shift,
        # which the frontend detects as "multiple chiefs" (主任席冲突).
        # With 6 leaders and 3 night shifts (each needing 1 leader),
        # the remaining 3 leaders are assigned to DAY shift.
        for day in self.work_days:
            for shift in chief_shifts:
                model.Add(sum(x[emp_id, day, shift] for emp_id in self.leader_ids) == 1)

        # Constraint 7: Avoidance group members cannot be in the same shift (硬约束)
        # This guarantees zero avoidance conflicts in the generated schedule.
        for emp1, emp2 in self.avoidance_pairs:
            if emp1 in self.emp_ids and emp2 in self.emp_ids:
                for day in self.work_days:
                    for shift in shift_types:
                        model.Add(x[emp1, day, shift] + x[emp2, day, shift] <= 1)

        # Constraint 7.5: 第一个员工只能上白班或睡觉班（硬约束）
        if len(self.emp_ids) > 0:
            first_emp_id = self.emp_ids[0]
            for day in self.work_days:
                for shift in [ShiftType.MINI_NIGHT, ShiftType.LATE_NIGHT]:
                    model.Add(x[first_emp_id, day, shift] == 0)

        # Constraint 7.6: 第一个员工按"1个白班 + 2个睡觉班"循环（硬约束，结合历史跨月数据）
        if len(self.emp_ids) > 0:
            first_emp_id = self.emp_ids[0]
            for i, day in enumerate(self.work_days):
                # 加上上个月的偏移量进行循环计算
                if (i + self.first_emp_offset) % 3 == 0:
                    # 白班
                    model.Add(x[first_emp_id, day, ShiftType.DAY] == 1)
                else:
                    # 睡觉班
                    model.Add(x[first_emp_id, day, ShiftType.SLEEP] == 1)

        # Constraint 7.65: 锁定的单元格约束（硬约束）
        # 用户锁定的单元格必须保持其班次类型不变
        for (emp_id, day), shift_type in self.locked_assignments.items():
            if emp_id in self.emp_ids and day in self.work_days:
                model.Add(x[emp_id, day, shift_type] == 1)

        # Constraint 7.7: 同一人连续夜班（SLEEP/MINI_NIGHT/LATE_NIGHT）不超过3个（硬约束）
        night_shifts = [ShiftType.SLEEP, ShiftType.MINI_NIGHT, ShiftType.LATE_NIGHT]
        for emp_id in self.emp_ids:
            for i in range(len(self.work_days) - 3):
                # 连续4天不能全是夜班
                four_day_nights = []
                for j in range(4):
                    day = self.work_days[i + j]
                    is_night = model.NewBoolVar(f"night_{emp_id}_{i}_{j}")
                    # is_night == 1 当且仅当该员工当天上任一夜班
                    model.Add(sum(x[emp_id, day, shift] for shift in night_shifts) >= is_night)
                    model.Add(sum(x[emp_id, day, shift] for shift in night_shifts) <= is_night * 3)
                    four_day_nights.append(is_night)
                # 4天中最多3个夜班
                model.Add(sum(four_day_nights) <= 3)

        # Constraint 7.8: 班次间隔约束
        # 普通席位大夜班：最少间隔3个班，最多间隔6个班
        # 主任席大夜班：最少间隔3个班，最多间隔5个班
        # 主任席白班：最少间隔1个班，最多间隔3个班
        leader_ids_set = set(self.leader_ids) if hasattr(self, 'leader_ids') else set(self.emp_ids[:6])
        from datetime import datetime

        max_gap_penalties = []

        for emp_id in self.emp_ids:
            is_leader = emp_id in leader_ids_set

            # --- 大夜班间隔 ---
            late_min_gap = 3  # 主任和普通都是最少3
            late_max_gap = 5 if is_leader else 6

            # 考虑上个月的大夜班历史（最小间隔）
            if emp_id in self.last_late_night:
                last_date = self.last_late_night[emp_id]
                last_dt = datetime.strptime(last_date, "%Y-%m-%d")

                for i, day in enumerate(self.work_days):
                    current_dt = datetime.strptime(day, "%Y-%m-%d")
                    days_since_last = (current_dt - last_dt).days

                    if days_since_last <= late_min_gap:
                        model.Add(x[emp_id, day, ShiftType.LATE_NIGHT] == 0)

            # 本月内大夜班最小间隔（硬约束）
            for i in range(len(self.work_days)):
                for j in range(1, late_min_gap + 1):
                    if i + j < len(self.work_days):
                        model.Add(
                            x[emp_id, self.work_days[i], ShiftType.LATE_NIGHT] +
                            x[emp_id, self.work_days[i + j], ShiftType.LATE_NIGHT] <= 1
                        )

            # 本月内大夜班最大间隔（软约束）
            # 如果第i天上大夜班，接下来 max_gap+1 天内应该再有一个大夜班
            for i in range(len(self.work_days)):
                end = min(i + late_max_gap + 2, len(self.work_days))
                if end - i < 2:
                    continue
                # 窗口内大夜班数量：如果第i天是大夜班，窗口内至少还要有1个
                window_days = [self.work_days[j] for j in range(i + 1, end)]
                if not window_days:
                    continue
                # 如果 x[i, LATE_NIGHT] == 1 且 sum(x[i+1..end, LATE_NIGHT]) == 0，则惩罚
                no_late_in_window = model.NewBoolVar(f"no_late_window_{emp_id}_{i}")
                model.Add(
                    sum(x[emp_id, d, ShiftType.LATE_NIGHT] for d in window_days) == 0
                ).OnlyEnforceIf(no_late_in_window)
                model.Add(
                    sum(x[emp_id, d, ShiftType.LATE_NIGHT] for d in window_days) >= 1
                ).OnlyEnforceIf(no_late_in_window.Not())

                gap_violation = model.NewBoolVar(f"late_gap_viol_{emp_id}_{i}")
                # gap_violation == 1 当且仅当 第i天是大夜班 且 窗口内没有大夜班
                model.AddBoolAnd([
                    x[emp_id, self.work_days[i], ShiftType.LATE_NIGHT],
                    no_late_in_window
                ]).OnlyEnforceIf(gap_violation)
                model.AddBoolOr([
                    x[emp_id, self.work_days[i], ShiftType.LATE_NIGHT].Not(),
                    no_late_in_window.Not()
                ]).OnlyEnforceIf(gap_violation.Not())

                max_gap_penalties.append(gap_violation)

           # --- 白班间隔（除第一人外所有人员） ---
            if emp_id != self.emp_ids[0]:  # 第一人有固定规则，排除
                day_min_gap = 1  # 最少间隔1个班
                day_max_gap = 3  # 最多间隔3个班

                is_staff = emp_id not in leader_ids_set

                # 1. 最小间隔约束
                if is_staff:
                    # 普通员工：硬约束（绝对不允许连续白班）
                    for i in range(len(self.work_days) - 1):
                        model.Add(
                            x[emp_id, self.work_days[i], ShiftType.DAY] +
                            x[emp_id, self.work_days[i + 1], ShiftType.DAY] <= 1
                        )
                else:
                    # 主任员工：硬约束 1（绝对不允许连续 3 天白班）
                    for i in range(len(self.work_days) - 2):
                        model.Add(
                            sum(x[emp_id, self.work_days[i+j], ShiftType.DAY] for j in range(3)) <= 2
                        )
                    
                    # 主任员工：硬约束 2（每月最多只允许出现 3 次两连白班，即极少数例外）
                    consec_pairs = []
                    for i in range(len(self.work_days) - 1):
                        pair = model.NewBoolVar(f"day_pair_{emp_id}_{i}")
                        # pair 变量绑定：连续两天白班时 pair 为 1，否则为 0
                        model.Add(
                            x[emp_id, self.work_days[i], ShiftType.DAY] +
                            x[emp_id, self.work_days[i + 1], ShiftType.DAY] >= 2
                        ).OnlyEnforceIf(pair)
                        model.Add(
                            x[emp_id, self.work_days[i], ShiftType.DAY] +
                            x[emp_id, self.work_days[i + 1], ShiftType.DAY] <= 1
                        ).OnlyEnforceIf(pair.Not())
                        consec_pairs.append(pair)
                        
                        # 把这仅有的几次连续作为软惩罚，让求解器在 <3 次的基础上尽量压到更少
                        max_gap_penalties.append(pair)
                    
                    # 硬性熔断：把所有两两连续的次数加起来，不得超过 3 次
                    model.Add(sum(consec_pairs) <= 3)

                # 2. 最大间隔约束（所有人适用：硬约束）
                # 间隔最多3天，意味着“任意连续的4天内，必须至少有1个白班”
                window_size = day_max_gap + 1  # 4
                for i in range(len(self.work_days) - window_size + 1):
                    window_days = [self.work_days[i+j] for j in range(window_size)]
                    model.Add(
                        sum(x[emp_id, d, ShiftType.DAY] for d in window_days) >= 1
                    )

        # Constraint 8: 尽量避免所有班次连续（软约束）
        # 对每个员工、每对相邻工作日、每种班次类型：
        # 如果同一人连续两天上同一种班，产生惩罚。
        # 权重极高(1000)，求解器会优先消除连续，实在排不开才允许。
        consecutive_penalties = []
        for emp_id in self.emp_ids:
            for i in range(len(self.work_days) - 1):
                day1 = self.work_days[i]
                day2 = self.work_days[i + 1]
                for shift in shift_types:
                    is_consecutive = model.NewBoolVar(
                        f"consec_{emp_id}_{i}_{shift.value}"
                    )
                    # is_consecutive == 1  iff  x[day1,shift] + x[day2,shift] == 2
                    model.Add(
                        x[emp_id, day1, shift] + x[emp_id, day2, shift]
                        <= 1 + is_consecutive
                    )
                    model.Add(
                        x[emp_id, day1, shift] + x[emp_id, day2, shift]
                        >= 2 * is_consecutive
                    )
                    consecutive_penalties.append(is_consecutive)

        # ============ Objective ============
        # 公平性：使用最小-最大差值法（min-max spread）
        # 关键改进：考虑连续两个月的班次总数，确保跨月公平性（规则4和6）
        # 对每个班次类型和每个员工组，最小化组内最大值与最小值的差

        deviations = []

        # 1. 普通员工公平性（索引6+）- 考虑两个月总数
        staff_ids = self.emp_ids[6:] if len(self.emp_ids) > 6 else []
        if len(staff_ids) > 1:
            for shift in shift_types:
                counts = []
                for emp_id in staff_ids:
                    # 本月班次数（决策变量）
                    current_cnt = model.NewIntVar(0, len(self.work_days), f"staff_{emp_id}_{shift.value}_current")
                    model.Add(current_cnt == sum(x[emp_id, day, shift] for day in self.work_days))

                    # 上个月班次数（常量）
                    prev_cnt = self.prev_shift_counts.get(emp_id, {}).get(shift, 0)

                    # 两个月总数
                    total_cnt = model.NewIntVar(0, len(self.work_days) * 2, f"staff_{emp_id}_{shift.value}_total")
                    model.Add(total_cnt == current_cnt + prev_cnt)
                    counts.append(total_cnt)

                max_cnt = model.NewIntVar(0, len(self.work_days) * 2, f"staff_max_{shift.value}")
                min_cnt = model.NewIntVar(0, len(self.work_days) * 2, f"staff_min_{shift.value}")
                model.AddMaxEquality(max_cnt, counts)
                model.AddMinEquality(min_cnt, counts)

                spread = model.NewIntVar(0, len(self.work_days) * 2, f"staff_spread_{shift.value}")
                model.Add(spread == max_cnt - min_cnt)
                deviations.append(spread)

        # 2. 主任员工公平性（索引1-5，第一个除外）- 考虑两个月总数
        leader_ids_excluding_first = self.emp_ids[1:6] if len(self.emp_ids) > 1 else []
        if len(leader_ids_excluding_first) > 1:
            for shift in shift_types:
                counts = []
                for emp_id in leader_ids_excluding_first:
                    # 本月班次数（决策变量）
                    current_cnt = model.NewIntVar(0, len(self.work_days), f"leader_{emp_id}_{shift.value}_current")
                    model.Add(current_cnt == sum(x[emp_id, day, shift] for day in self.work_days))

                    # 上个月班次数（常量）
                    prev_cnt = self.prev_shift_counts.get(emp_id, {}).get(shift, 0)

                    # 两个月总数
                    total_cnt = model.NewIntVar(0, len(self.work_days) * 2, f"leader_{emp_id}_{shift.value}_total")
                    model.Add(total_cnt == current_cnt + prev_cnt)
                    counts.append(total_cnt)

                max_cnt = model.NewIntVar(0, len(self.work_days) * 2, f"leader_max_{shift.value}")
                min_cnt = model.NewIntVar(0, len(self.work_days) * 2, f"leader_min_{shift.value}")
                model.AddMaxEquality(max_cnt, counts)
                model.AddMinEquality(min_cnt, counts)

                spread = model.NewIntVar(0, len(self.work_days) * 2, f"leader_spread_{shift.value}")
                model.Add(spread == max_cnt - min_cnt)
                deviations.append(spread)

        # Combined objective:
        #   连续惩罚 1000 >> 间隔惩罚 500 >> 公平性 200 >> 随机扰动 0-3
        #   公平性权重提高到200，确保班次分配均匀
        import random
        consecutive_weight = 1000
        variance_weight = 200

        # 为每个员工每天的班次分配添加微小的随机偏好
        random_terms = []
        for emp_id in self.emp_ids:
            for day in self.work_days:
                for shift in shift_types:
                    coeff = random.randint(0, 3)
                    if coeff > 0:
                        random_terms.append(coeff * x[emp_id, day, shift])

        model.Minimize(
            consecutive_weight * sum(consecutive_penalties)
            + 500 * sum(max_gap_penalties)
            + variance_weight * sum(deviations)
            + sum(random_terms)
        )

        # Solve
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 30.0
        # 每次求解使用不同的随机种子，生成不同的排班方案
        solver.parameters.random_seed = random.randint(0, 2**31 - 1)
        status = solver.Solve(model)

        if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            raise ValueError(f"No solution found. Solver status: {status}")

        # Extract solution
        schedules = self._extract_solution(solver, x, c, shift_types, chief_shifts)
        stats = self._calculate_statistics(solver, x)

        return schedules, stats

    def _extract_solution(
        self,
        solver: cp_model.CpSolver,
        x: dict,
        c: dict,
        shift_types: list[ShiftType],
        chief_shifts: list[ShiftType],
    ) -> list[DailySchedule]:
        """Extract the schedule from the solver solution."""
        schedules = []

        for day in self.work_days:
            records = []

            # Track assignments per shift for slot allocation
            shift_assignments: dict[ShiftType, list[str]] = defaultdict(list)
            chief_assignments: dict[ShiftType, str] = {}

            # First pass: identify all assignments
            for emp_id in self.emp_ids:
                for shift in shift_types:
                    if solver.Value(x[emp_id, day, shift]) == 1:
                        shift_assignments[shift].append(emp_id)

            # Identify chiefs
            for emp_id in self.leader_ids:
                for shift in chief_shifts:
                    if (emp_id, day, shift) in c and solver.Value(c[emp_id, day, shift]) == 1:
                        chief_assignments[shift] = emp_id

            # Second pass: create records with slot types
            for shift, emp_ids in shift_assignments.items():
                slot_config = SLOT_CONFIG[shift]
                slot_queue = []

                # Build slot queue
                for slot_type, count, requires_leader in slot_config:
                    for _ in range(count):
                        slot_queue.append((slot_type, requires_leader))

                # Assign chiefs first
                assigned = set()
                if shift in chief_shifts and shift in chief_assignments:
                    chief_id = chief_assignments[shift]
                    chief_slot = next(
                        (s for s, req in slot_queue if req), slot_queue[0]
                    )
                    records.append(
                        ShiftRecord(
                            employee_id=chief_id,
                            date=day,
                            shift_type=shift,
                            slot_type=chief_slot[0] if isinstance(chief_slot, tuple) else chief_slot,
                        )
                    )
                    assigned.add(chief_id)
                    # Remove chief slot from queue
                    slot_queue = [(s, r) for s, r in slot_queue if not r]

                # Assign remaining employees
                remaining_emps = [e for e in emp_ids if e not in assigned]
                for i, emp_id in enumerate(remaining_emps):
                    if i < len(slot_queue):
                        slot_type = slot_queue[i][0]
                    else:
                        # Fallback
                        slot_type = slot_config[0][0]
                    records.append(
                        ShiftRecord(
                            employee_id=emp_id,
                            date=day,
                            shift_type=shift,
                            slot_type=slot_type,
                        )
                    )

            # Sort records by employee order
            emp_order = {emp_id: i for i, emp_id in enumerate(self.emp_ids)}
            records.sort(key=lambda r: emp_order.get(r.employee_id, 999))

            schedules.append(
                DailySchedule(
                    date=day,
                    day_of_week=get_day_of_week_cn(day),
                    records=records,
                )
            )

        return schedules

    def _calculate_statistics(
        self,
        solver: cp_model.CpSolver,
        x: dict,
    ) -> dict:
        """Calculate statistics for the generated schedule.

        Includes both current month and two-month cumulative statistics
        to show fairness across months (规则4和6).
        """
        shift_types = [ShiftType.DAY, ShiftType.SLEEP, ShiftType.MINI_NIGHT, ShiftType.LATE_NIGHT]

        # Count shifts per employee for current month
        emp_shift_counts = defaultdict(lambda: defaultdict(int))
        for emp_id in self.emp_ids:
            for day in self.work_days:
                for shift in shift_types:
                    if solver.Value(x[emp_id, day, shift]) == 1:
                        emp_shift_counts[emp_id][shift.value] += 1

        # Calculate two-month cumulative counts (current + previous)
        emp_two_month_counts = defaultdict(lambda: defaultdict(int))
        for emp_id in self.emp_ids:
            for shift in shift_types:
                current_count = emp_shift_counts[emp_id][shift.value]
                prev_count = self.prev_shift_counts.get(emp_id, {}).get(shift, 0)
                emp_two_month_counts[emp_id][shift.value] = current_count + prev_count

        # Calculate distribution for each shift type (current month)
        shift_distributions = {}
        for shift in shift_types:
            values = [emp_shift_counts[emp_id][shift.value] for emp_id in self.emp_ids]
            shift_std = statistics.stdev(values) if len(values) > 1 else 0
            shift_distributions[shift.value] = {
                "min": min(values),
                "max": max(values),
                "avg": round(sum(values) / len(values), 2),
                "std_dev": round(shift_std, 2),
                "spread": max(values) - min(values),
            }

        # Calculate two-month distribution (for fairness analysis)
        two_month_distributions = {}
        for shift in shift_types:
            values = [emp_two_month_counts[emp_id][shift.value] for emp_id in self.emp_ids]
            if len(values) > 1:
                shift_std = statistics.stdev(values)
                two_month_distributions[shift.value] = {
                    "min": min(values),
                    "max": max(values),
                    "avg": round(sum(values) / len(values), 2),
                    "std_dev": round(shift_std, 2),
                    "spread": max(values) - min(values),
                }

        # Calculate fairness score (lower is better)
        # Sum of spreads across all shift types for two-month period
        fairness_score = sum(
            two_month_distributions.get(shift.value, {}).get("spread", 0)
            for shift in shift_types
        )

        return {
            "total_work_days": len(self.work_days),
            "employee_shift_counts": dict(emp_shift_counts),
            "shift_distributions": shift_distributions,
            "two_month_distributions": two_month_distributions,
            "two_month_employee_counts": dict(emp_two_month_counts),
            "fairness_score": fairness_score,
            "has_previous_data": len(self.previous_schedules) > 0,
        }
