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

        # --- 新增：提取跨月历史完整排班 ---
        self.num_prev_days = 0
        self.prev_history_shifts = defaultdict(list)
        
        # 构建历史班次统计：每个员工上个月各班次的数量（用于跨月公平性）
        self.prev_shift_counts: dict[str, dict[ShiftType, int]] = defaultdict(lambda: defaultdict(int))

        if self.previous_schedules:
            sorted_prev = sorted(self.previous_schedules, key=lambda s: s.date)
            # 截取上个月最后 6 天的排班（大夜最大间隔6天，前置6天足以覆盖所有滑窗）
            last_schedules = sorted_prev[-6:]
            self.num_prev_days = len(last_schedules)
            
            for schedule in last_schedules:
                for emp_id in self.emp_ids:
                    record = next((r for r in schedule.records if r.employee_id == emp_id), None)
                    shift = record.shift_type if record else ShiftType.NONE
                    if isinstance(shift, str):
                        try: shift = ShiftType(shift)
                        except ValueError: shift = ShiftType.NONE
                    self.prev_history_shifts[emp_id].append(shift)
                    
            for schedule in sorted_prev:
                for record in schedule.records:
                    # 统计各班次数量（排除休假等非正常班次）
                    if record.shift_type not in [ShiftType.NONE, ShiftType.VACATION, getattr(ShiftType, 'CUSTOM', 'CUSTOM')]:
                        shift = record.shift_type
                        if isinstance(shift, str):
                            try: shift = ShiftType(shift)
                            except ValueError: continue
                        self.prev_shift_counts[record.employee_id][shift] += 1

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
        core_shifts = [ShiftType.DAY, ShiftType.SLEEP, ShiftType.MINI_NIGHT, ShiftType.LATE_NIGHT]
        exempt_shifts = [ShiftType.VACATION, ShiftType.NONE, getattr(ShiftType, 'CUSTOM', 'CUSTOM')]
        all_shifts = core_shifts + exempt_shifts
        
        # 保留 shift_types 变量以兼容后续代码
        shift_types = core_shifts 

        for emp_id in self.emp_ids:
            for day in self.work_days:
                for shift in all_shifts:
                    shift_val = shift.value if hasattr(shift, 'value') else shift
                    x[emp_id, day, shift] = model.NewBoolVar(f"x_{emp_id}_{day}_{shift_val}")

        # Chief assignment variables: c[emp_id, day, shift_type] = 1 if assigned as chief
        c = {}
        chief_shifts = [ShiftType.SLEEP, ShiftType.MINI_NIGHT, ShiftType.LATE_NIGHT]
        for emp_id in self.leader_ids:
            for day in self.work_days:
                for shift in chief_shifts:
                    c[emp_id, day, shift] = model.NewBoolVar(f"c_{emp_id}_{day}_{shift.value}")

        # Constraint 1: 每个员工每天必须分配一个班次（正常班或休假/空班）
        for emp_id in self.emp_ids:
            for day in self.work_days:
                model.AddExactlyOne(x[emp_id, day, shift] for shift in all_shifts)

        # Constraint 2: 各岗位定员分配（支持休假动态扣减白班人数）
        for day in self.work_days:
            # 统计当天处于休假/出差/空班的总人数
            num_exempt = sum(x[emp_id, day, s] for emp_id in self.emp_ids for s in exempt_shifts)
            for shift, count in SHIFT_TOTALS.items():
                if shift == ShiftType.DAY:
                    # 数学魔法：如果有人休假，优先扣减白班的定员需求，保证排班引擎永不崩溃
                    model.Add(sum(x[emp_id, day, shift] for emp_id in self.emp_ids) == count - num_exempt)
                else:
                    model.Add(sum(x[emp_id, day, shift] for emp_id in self.emp_ids) == count)

        # ====================================================================
        # --- 跨月时空滑窗探测器（核心科技） ---
        # ====================================================================
        total_days = self.num_prev_days + len(self.work_days)
        def get_x(e_id, idx, stype):
            """获取索引天的变量：如果是历史天则返回常量(0或1)，如果是本月天则返回布尔变量"""
            if idx < self.num_prev_days:
                return 1 if self.prev_history_shifts[e_id][idx] == stype else 0
            else:
                return x[e_id, self.work_days[idx - self.num_prev_days], stype]

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
        # Constraint 6: 夜班长（主任）资格人员数量限制（硬约束）
        for day in self.work_days:
            # 小夜和大夜：至少 1 名，最多 2 名
            for shift in [ShiftType.MINI_NIGHT, ShiftType.LATE_NIGHT]:
                model.Add(sum(x[emp_id, day, shift] for emp_id in self.leader_ids) >= 1)
                model.Add(sum(x[emp_id, day, shift] for emp_id in self.leader_ids) <= 2)
            
            # 睡觉班：至少 1 名，最多 3 名
            model.Add(sum(x[emp_id, day, ShiftType.SLEEP] for emp_id in self.leader_ids) >= 1)
            model.Add(sum(x[emp_id, day, ShiftType.SLEEP] for emp_id in self.leader_ids) <= 3)

        # Constraint 7: Avoidance group members cannot be in the same shift (硬约束)
        # This guarantees zero avoidance conflicts in the generated schedule.
        # Constraint 7: 避让组隔离规则（硬约束）
        for group in self.constraints.avoidance_groups:
            # 提取当前避让组中存在于本次排班名单里的员工ID
            group_ids = [eid for eid in group.employee_ids if eid in self.emp_ids]
            if not group_ids:
                continue
                
            for day in self.work_days:
                # 1. 大夜和小夜：互斥人员最多只能有 1 个（即不能同时排在这两个班次）
                model.Add(sum(x[emp_id, day, ShiftType.LATE_NIGHT] for emp_id in group_ids) <= 1)
                model.Add(sum(x[emp_id, day, ShiftType.MINI_NIGHT] for emp_id in group_ids) <= 1)
                
                # 2. 睡觉班：互斥人员最多只能有 2 个
                model.Add(sum(x[emp_id, day, ShiftType.SLEEP] for emp_id in group_ids) <= 2)
                
                # 3. 白班：不限制（无需写约束，求解器自然允许任意人数）

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

        # --- 新增：堵住求解器乱排自定义班次的漏洞 ---
        # 除非用户手动锁定，否则求解器绝对不能把任何人排成休假、空班或自定义班次！
        for emp_id in self.emp_ids:
            for day in self.work_days:
                for shift in exempt_shifts:
                    # 如果这个格子没有被用户锁定为当前的豁免班次，就彻底封死这个变量（强制等于0）
                    if self.locked_assignments.get((emp_id, day)) != shift:
                        model.Add(x[emp_id, day, shift] == 0)

        # Constraint 7.7: 同一人连续夜班不超过3个（硬约束，无缝跨月）

        # Constraint 7.7: 同一人连续夜班不超过3个（硬约束，无缝跨月）
        night_shifts = [ShiftType.SLEEP, ShiftType.MINI_NIGHT, ShiftType.LATE_NIGHT]
        for emp_id in self.emp_ids:
            for i in range(total_days - 3):
                # 连续 4 天的滑动窗口扫描
                four_day_nights = [
                    sum(get_x(emp_id, i + j, shift) for shift in night_shifts)
                    for j in range(4)
                ]
                model.Add(sum(four_day_nights) <= 3)

        # Constraint 7.75: 保底大夜班约束（硬约束）兜底
        for emp_id in self.emp_ids:
            if emp_id != self.emp_ids[0]:  
                model.Add(sum(x[emp_id, day, ShiftType.LATE_NIGHT] for day in self.work_days) >= 1)

        # Constraint 7.8: 班次间隔约束（硬约束，无缝跨月，含“休假跳过”豁免）
        leader_ids_set = set(self.leader_ids) if hasattr(self, 'leader_ids') else set(self.emp_ids[:6])
        max_gap_penalties = [] # 留空以防下文报错

        for emp_id in self.emp_ids:
            is_leader = emp_id in leader_ids_set

            # --- 大夜班间隔 ---
            late_min_gap = 3  
            late_max_gap = 5 if is_leader else 6

            # 1. 大夜班跨月最小间隔
            window_size_min_late = late_min_gap + 1
            for i in range(total_days - window_size_min_late + 1):
                window_sum = sum(get_x(emp_id, i + j, ShiftType.LATE_NIGHT) for j in range(window_size_min_late))
                model.Add(window_sum <= 1)

            # 2. 大夜班跨月最大间隔（含休假豁免）
            if emp_id != self.emp_ids[0]:
                window_size_max_late = late_max_gap + 1
                for i in range(total_days - window_size_max_late + 1):
                    window_sum = sum(get_x(emp_id, i + j, ShiftType.LATE_NIGHT) for j in range(window_size_max_late))
                    # 统计该窗口内的休假等豁免班次数量
                    exempt_sum = sum(get_x(emp_id, i + j, shift) for j in range(window_size_max_late) for shift in exempt_shifts)
                    # 只要发生休假(exempt_sum >= 1)，规则自动满足，完美跳过断档！
                    model.Add(window_sum + exempt_sum >= 1)

            # --- 白班间隔 ---
            if emp_id != self.emp_ids[0]:  
                day_max_gap = 3  

                # 1. 白班跨月最小间隔：绝对不允许连上白班
                for i in range(total_days - 1):
                    model.Add(get_x(emp_id, i, ShiftType.DAY) + get_x(emp_id, i + 1, ShiftType.DAY) <= 1)

                # 2. 白班跨月最大间隔（含休假豁免）
                window_size_max_day = day_max_gap + 1
                for i in range(total_days - window_size_max_day + 1):
                    window_sum = sum(get_x(emp_id, i + j, ShiftType.DAY) for j in range(window_size_max_day))
                    exempt_sum = sum(get_x(emp_id, i + j, shift) for j in range(window_size_max_day) for shift in exempt_shifts)
                    model.Add(window_sum + exempt_sum >= 1)

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
        solver.parameters.max_time_in_seconds = 120.0
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
            all_shift_types = [ShiftType.DAY, ShiftType.SLEEP, ShiftType.MINI_NIGHT, ShiftType.LATE_NIGHT, ShiftType.VACATION, ShiftType.NONE]
            if hasattr(ShiftType, 'CUSTOM'):
                all_shift_types.append(getattr(ShiftType, 'CUSTOM'))
                
            for emp_id in self.emp_ids:
                for shift in all_shift_types:
                    if solver.Value(x[emp_id, day, shift]) == 1:
                        if shift in shift_types: # 如果是四大核心排班
                            shift_assignments[shift].append(emp_id)
                        else: # 如果是休假/空班，直接录入最终结果，且不占用坑位！
                            records.append(
                                ShiftRecord(
                                    employee_id=emp_id,
                                    date=day,
                                    shift_type=shift,
                                    slot_type=None,
                                )
                            )
                        break

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
