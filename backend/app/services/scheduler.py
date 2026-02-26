"""Scheduling solver using Google OR-Tools CP-SAT solver."""

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
    ):
        self.employees = employees
        self.work_days = work_days
        self.constraints = constraints
        self.previous_schedules = previous_schedules or []

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
        if self.previous_schedules:
            sorted_prev = sorted(self.previous_schedules, key=lambda s: s.date)
            for schedule in sorted_prev:
                for record in schedule.records:
                    if record.shift_type == ShiftType.LATE_NIGHT:
                        self.last_late_night[record.employee_id] = schedule.date

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

        # Constraint 7.6: 第一个员工按"1个白班 + 2个睡觉班"循环（硬约束）
        if len(self.emp_ids) > 0:
            first_emp_id = self.emp_ids[0]
            for i, day in enumerate(self.work_days):
                if i % 3 == 0:
                    # 白班
                    model.Add(x[first_emp_id, day, ShiftType.DAY] == 1)
                else:
                    # 睡觉班
                    model.Add(x[first_emp_id, day, ShiftType.SLEEP] == 1)

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
                day_min_gap = 1  # 最少间隔1个班（尽量不连续白班）
                day_max_gap = 3  # 最多间隔3个班

                is_staff = emp_id not in leader_ids_set

                if is_staff:
                    # 普通员工白班最小间隔（硬约束）
                    # 11人分3个白班位，每人约8个白班/月，完全可行
                    for i in range(len(self.work_days)):
                        for j in range(1, day_min_gap + 1):
                            if i + j < len(self.work_days):
                                model.Add(
                                    x[emp_id, self.work_days[i], ShiftType.DAY] +
                                    x[emp_id, self.work_days[i + j], ShiftType.DAY] <= 1
                                )
                else:
                    # 主任员工白班最小间隔（软约束）
                    # 5人分3个白班位，每人约18个白班/月，无法完全避免连续
                    for i in range(len(self.work_days)):
                        for j in range(1, day_min_gap + 1):
                            if i + j < len(self.work_days):
                                consec_day = model.NewBoolVar(f"consec_day_{emp_id}_{i}_{j}")
                                model.Add(
                                    x[emp_id, self.work_days[i], ShiftType.DAY] +
                                    x[emp_id, self.work_days[i + j], ShiftType.DAY] >= 2
                                ).OnlyEnforceIf(consec_day)
                                model.Add(
                                    x[emp_id, self.work_days[i], ShiftType.DAY] +
                                    x[emp_id, self.work_days[i + j], ShiftType.DAY] <= 1
                                ).OnlyEnforceIf(consec_day.Not())
                                max_gap_penalties.append(consec_day)

                # 白班最大间隔（软约束）
                for i in range(len(self.work_days)):
                    end = min(i + day_max_gap + 2, len(self.work_days))
                    if end - i < 2:
                        continue
                    window_days = [self.work_days[j] for j in range(i + 1, end)]
                    if not window_days:
                        continue

                    no_day_in_window = model.NewBoolVar(f"no_day_window_{emp_id}_{i}")
                    model.Add(
                        sum(x[emp_id, d, ShiftType.DAY] for d in window_days) == 0
                    ).OnlyEnforceIf(no_day_in_window)
                    model.Add(
                        sum(x[emp_id, d, ShiftType.DAY] for d in window_days) >= 1
                    ).OnlyEnforceIf(no_day_in_window.Not())

                    day_gap_violation = model.NewBoolVar(f"day_gap_viol_{emp_id}_{i}")
                    model.AddBoolAnd([
                        x[emp_id, self.work_days[i], ShiftType.DAY],
                        no_day_in_window
                    ]).OnlyEnforceIf(day_gap_violation)
                    model.AddBoolOr([
                        x[emp_id, self.work_days[i], ShiftType.DAY].Not(),
                        no_day_in_window.Not()
                    ]).OnlyEnforceIf(day_gap_violation.Not())

                    max_gap_penalties.append(day_gap_violation)

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
        # 对每个班次类型和每个员工组，最小化组内最大值与最小值的差
        # 不需要预计算平均值，避免因分组共享导致的目标偏差

        deviations = []

        # 1. 普通员工公平性（索引6+）
        staff_ids = self.emp_ids[6:] if len(self.emp_ids) > 6 else []
        if len(staff_ids) > 1:
            for shift in shift_types:
                counts = []
                for emp_id in staff_ids:
                    cnt = model.NewIntVar(0, len(self.work_days), f"staff_{emp_id}_{shift.value}_cnt")
                    model.Add(cnt == sum(x[emp_id, day, shift] for day in self.work_days))
                    counts.append(cnt)

                max_cnt = model.NewIntVar(0, len(self.work_days), f"staff_max_{shift.value}")
                min_cnt = model.NewIntVar(0, len(self.work_days), f"staff_min_{shift.value}")
                model.AddMaxEquality(max_cnt, counts)
                model.AddMinEquality(min_cnt, counts)

                spread = model.NewIntVar(0, len(self.work_days), f"staff_spread_{shift.value}")
                model.Add(spread == max_cnt - min_cnt)
                deviations.append(spread)

        # 2. 主任员工公平性（索引1-5，第一个除外）
        leader_ids_excluding_first = self.emp_ids[1:6] if len(self.emp_ids) > 1 else []
        if len(leader_ids_excluding_first) > 1:
            for shift in shift_types:
                counts = []
                for emp_id in leader_ids_excluding_first:
                    cnt = model.NewIntVar(0, len(self.work_days), f"leader_{emp_id}_{shift.value}_cnt")
                    model.Add(cnt == sum(x[emp_id, day, shift] for day in self.work_days))
                    counts.append(cnt)

                max_cnt = model.NewIntVar(0, len(self.work_days), f"leader_max_{shift.value}")
                min_cnt = model.NewIntVar(0, len(self.work_days), f"leader_min_{shift.value}")
                model.AddMaxEquality(max_cnt, counts)
                model.AddMinEquality(min_cnt, counts)

                spread = model.NewIntVar(0, len(self.work_days), f"leader_spread_{shift.value}")
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
        """Calculate statistics for the generated schedule."""
        shift_types = [ShiftType.DAY, ShiftType.SLEEP, ShiftType.MINI_NIGHT, ShiftType.LATE_NIGHT]

        # Count shifts per employee
        emp_shift_counts = defaultdict(lambda: defaultdict(int))
        for emp_id in self.emp_ids:
            for day in self.work_days:
                for shift in shift_types:
                    if solver.Value(x[emp_id, day, shift]) == 1:
                        emp_shift_counts[emp_id][shift.value] += 1

        # Calculate distribution for each shift type
        shift_distributions = {}
        for shift in shift_types:
            values = [emp_shift_counts[emp_id][shift.value] for emp_id in self.emp_ids]
            shift_std = statistics.stdev(values) if len(values) > 1 else 0
            shift_distributions[shift.value] = {
                "min": min(values),
                "max": max(values),
                "avg": round(sum(values) / len(values), 2),
                "std_dev": round(shift_std, 2),
            }

        return {
            "total_work_days": len(self.work_days),
            "employee_shift_counts": dict(emp_shift_counts),
            "shift_distributions": shift_distributions,
        }
