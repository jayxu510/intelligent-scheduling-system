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
        """Solve the scheduling problem."""
        
        
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

        # Constraint 6: 夜班长（主任）资格人员数量限制（硬约束）
        sleep_chief_3_penalties = []  # 新增：记录睡觉班排了3个主任的情况，用于后续扣分
        
        for day in self.work_days:
            # 小夜和大夜：有且仅有 1 名主任（严苛硬约束）
            for shift in [ShiftType.MINI_NIGHT, ShiftType.LATE_NIGHT]:
                model.Add(sum(x[emp_id, day, shift] for emp_id in self.leader_ids) == 1)
            
            # 睡觉班：至少 1 名，最多 3 名（硬约束放宽上限）
            sleep_chiefs_expr = sum(x[emp_id, day, ShiftType.SLEEP] for emp_id in self.leader_ids)
            model.Add(sleep_chiefs_expr >= 1)
            model.Add(sleep_chiefs_expr <= 3)
            
            # 软约束打分标记：如果睡觉班排了 3 个主任，就把 has_3_sleep_chiefs 置为 1
            has_3_sleep_chiefs = model.NewBoolVar(f'sleep_chief_3_{day}')
            model.Add(sleep_chiefs_expr == 3).OnlyEnforceIf(has_3_sleep_chiefs)
            model.Add(sleep_chiefs_expr < 3).OnlyEnforceIf(has_3_sleep_chiefs.Not())
            sleep_chief_3_penalties.append(has_3_sleep_chiefs)

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

        # =======================================================
        # Constraint 7.62: 前两名员工（值班经理）白班互斥（硬约束）
        # 第一和第二个人绝对不能在同一天上白班
        # =======================================================
        if len(self.emp_ids) >= 2:
            manager_1_id = self.emp_ids[0]
            manager_2_id = self.emp_ids[1]
            for day in self.work_days:
                # 两人在同一天的白班状态相加必须 <= 1 (即不可能同时为1)
                model.Add(
                    x[manager_1_id, day, ShiftType.DAY] + 
                    x[manager_2_id, day, ShiftType.DAY] <= 1
                )

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
        night_shifts = [ShiftType.SLEEP, ShiftType.MINI_NIGHT, ShiftType.LATE_NIGHT]
        for emp_id in self.emp_ids:
            for i in range(total_days - 3):
                # 连续 4 天的滑动窗口扫描
                four_day_nights = [
                    sum(get_x(emp_id, i + j, shift) for shift in night_shifts)
                    for j in range(4)
                ]
                model.Add(sum(four_day_nights) <= 3)

        # --- 修复报错：提前在这里初始化列表 ---
        max_gap_penalties = [] 
        min_gap_penalties = [] # <--- 新增这行，用来装最小间隔的扣分

        # Constraint 7.75: 保底大夜班约束（降级为软约束，防死机）
        for emp_id in self.emp_ids:
            if emp_id != self.emp_ids[0]:  
                no_late_night = model.NewBoolVar(f'no_late_night_{emp_id}')
                model.Add(sum(x[emp_id, day, ShiftType.LATE_NIGHT] for day in self.work_days) == 0).OnlyEnforceIf(no_late_night)
                model.Add(sum(x[emp_id, day, ShiftType.LATE_NIGHT] for day in self.work_days) >= 1).OnlyEnforceIf(no_late_night.Not())
                max_gap_penalties.append(no_late_night)  # 借用下方惩罚分，违规一次重罚

        # Constraint 7.8: 班次间隔约束
        leader_ids_set = set(self.leader_ids) if hasattr(self, 'leader_ids') else set(self.emp_ids[:6])
        # (这里原本的 max_gap_penalties = [] 已经被删掉了)

        # 小夜班间隔目标分布（来自样本：0:1,1:4,2:5,3:3,4:9,5:7,6:2,7:3,8:1）
        # 这里按用户要求采用 1~8 天区间，并按概率分层设置惩罚权重（概率越高惩罚越低）
        mini_gap_probabilities = {
            1: 4 / 35,
            2: 5 / 35,
            3: 3 / 35,
            4: 9 / 35,
            5: 7 / 35,
            6: 2 / 35,
            7: 3 / 35,
            8: 1 / 35,
        }
        mini_gap_weight_by_gap = {}
        for gap, prob in mini_gap_probabilities.items():
            if prob >= 0.20:        # 高概率区（4,5）
                mini_gap_weight_by_gap[gap] = 200
            elif prob >= 0.10:      # 次高概率区（1,2）
                mini_gap_weight_by_gap[gap] = 500
            elif prob >= 0.08:      # 中概率区（3,7）
                mini_gap_weight_by_gap[gap] = 900
            else:                   # 低概率区（6,8）
                mini_gap_weight_by_gap[gap] = 1300

        mini_gap_penalty_terms = []
        mini_gap_gt_8_penalties = []
        sleep_gap_penalty_terms = []

        for emp_id in self.emp_ids:
            is_leader = emp_id in leader_ids_set

            # --- 大夜班间隔 ---
            late_min_gap = 3
            late_max_gap = 5 if is_leader else 6

            # 1. 大夜班跨月最小间隔
            window_size_min_late = late_min_gap + 1
            for i in range(total_days - window_size_min_late + 1):
                window_sum = sum(get_x(emp_id, i + j, ShiftType.LATE_NIGHT) for j in range(window_size_min_late))
                # 如果这个 4 天窗口里出现 2 个大夜班（即只隔了 1~2 天），触发惩罚
                min_gap_violated = model.NewBoolVar(f'late_min_viol_{emp_id}_{i}')
                model.Add(window_sum > 1).OnlyEnforceIf(min_gap_violated)
                model.Add(window_sum <= 1).OnlyEnforceIf(min_gap_violated.Not())

                min_gap_penalties.append(min_gap_violated)

            # 2. 大夜班跨月最大间隔（降级为软约束：休假算作间隔，但排不开时重罚而不是死机）
            if emp_id != self.emp_ids[0]:
                window_size_max_late = late_max_gap + 1
                for i in range(total_days - window_size_max_late + 1):
                    window_sum = sum(get_x(emp_id, i + j, ShiftType.LATE_NIGHT) for j in range(window_size_max_late))

                    gap_violated = model.NewBoolVar(f'late_gap_viol_{emp_id}_{i}')
                    model.Add(window_sum == 0).OnlyEnforceIf(gap_violated)
                    model.Add(window_sum >= 1).OnlyEnforceIf(gap_violated.Not())

                    max_gap_penalties.append(gap_violated)

            # --- 小夜班间隔（按 1~8 天）---
            # 修复 1：必须排除第一名员工（他不上小夜）
            if emp_id != self.emp_ids[0]:  
                
                # 修复 2：将硬约束降级为软约束（防休假死机）。连续9天最好有1个小夜班，否则重罚。
                for i in range(total_days - 8):
                    window_sum = sum(get_x(emp_id, i + j, ShiftType.MINI_NIGHT) for j in range(9))
                    gap_violated = model.NewBoolVar(f'mini_max_gap_viol_{emp_id}_{i}')
                    model.Add(window_sum == 0).OnlyEnforceIf(gap_violated)
                    model.Add(window_sum >= 1).OnlyEnforceIf(gap_violated.Not())
                    mini_gap_gt_8_penalties.append(gap_violated)

                # 2) 软约束：按样本概率分层权重，惩罚“相邻两次小夜班”的间隔类型
                # （Cursor 写的这段逻辑不错，我们保留，只需要缩进一下）
                for i in range(total_days - 1):
                    for j in range(i + 1, total_days):
                        gap = j - i
                        is_next_mini_pair = model.NewBoolVar(f'mini_pair_{emp_id}_{i}_{j}')

                        current_is_mini = get_x(emp_id, i, ShiftType.MINI_NIGHT)
                        next_is_mini = get_x(emp_id, j, ShiftType.MINI_NIGHT)

                        # 上界：必须两端都是小夜班
                        model.Add(is_next_mini_pair <= current_is_mini)
                        model.Add(is_next_mini_pair <= next_is_mini)

                        # 上界：中间不能再出现小夜班（确保是“相邻两次小夜班”）
                        for k in range(i + 1, j):
                            model.Add(is_next_mini_pair <= 1 - get_x(emp_id, k, ShiftType.MINI_NIGHT))

                        # 下界：两端是小夜班且中间都不是小夜班时，必须激活该变量
                        middle_clear_terms = [1 - get_x(emp_id, k, ShiftType.MINI_NIGHT) for k in range(i + 1, j)]
                        required_terms = [current_is_mini, next_is_mini] + middle_clear_terms
                        model.Add(is_next_mini_pair >= sum(required_terms) - (len(required_terms) - 1))

                        if 1 <= gap <= 8:
                            mini_gap_penalty_terms.append(mini_gap_weight_by_gap[gap] * is_next_mini_pair)
                        else:
                            mini_gap_gt_8_penalties.append(is_next_mini_pair)

            # --- 白班间隔 ---
            if emp_id != self.emp_ids[0]:
                day_max_gap = 3

                # 1. 白班跨月最小间隔：防连轴转（包含休假后不能直接上白班），绝对底线
                for i in range(total_days - 1):
                    # 把前一天的 白班、休假、自定义、空班 全部视为“广义白班”
                    yesterday_day_or_exempt = get_x(emp_id, i, ShiftType.DAY) + sum(get_x(emp_id, i, s) for s in exempt_shifts)
                    # 如果昨天是“广义白班”，今天绝对不能排白班
                    model.Add(yesterday_day_or_exempt + get_x(emp_id, i + 1, ShiftType.DAY) <= 1)

                # 2. 白班跨月最大间隔（降级为软约束：排不开时重罚而不是死机）
                window_size_max_day = day_max_gap + 1
                for i in range(total_days - window_size_max_day + 1):
                    window_sum = sum(get_x(emp_id, i + j, ShiftType.DAY) for j in range(window_size_max_day))

                    gap_violated = model.NewBoolVar(f'day_gap_viol_{emp_id}_{i}')
                    model.Add(window_sum == 0).OnlyEnforceIf(gap_violated)
                    model.Add(window_sum >= 1).OnlyEnforceIf(gap_violated.Not())

                    max_gap_penalties.append(gap_violated)

            # ==========================================
            # --- 睡觉班专属间隔惩罚（软约束） ---
            # ==========================================
            if emp_id != self.emp_ids[0]:
                # 1. 间隔 6 天及以上重罚（任何连续 6 天没有睡觉班，每天扣 1000 分）
                window_size_sleep = 6
                for i in range(total_days - window_size_sleep + 1):
                    window_sum = sum(get_x(emp_id, i + j, ShiftType.SLEEP) for j in range(window_size_sleep))
                    gap_violated = model.NewBoolVar(f'sleep_max_gap_viol_{emp_id}_{i}')
                    model.Add(window_sum == 0).OnlyEnforceIf(gap_violated)
                    model.Add(window_sum >= 1).OnlyEnforceIf(gap_violated.Not())
                    sleep_gap_penalty_terms.append(1000 * gap_violated)

                # 2. 间隔 1~5 天的分层扣分（删除了 0 天的情况）
                sleep_gap_weights = {1: 100, 2: 0, 3: 100, 4: 300, 5: 300}
                for i in range(total_days - 1):
                    # j 是下一次上睡觉班的位置，最多往后扫描 6 天（即对应 gap=5）
                    for j in range(i + 1, min(i + 7, total_days)): 
                        gap = (j - i) - 1  # 算出中间隔了几天
                        weight = sleep_gap_weights.get(gap, 0)
                        
                        if weight > 0:
                            is_next_sleep = model.NewBoolVar(f'sleep_pair_{emp_id}_{i}_{j}')
                            current_is_sleep = get_x(emp_id, i, ShiftType.SLEEP)
                            next_is_sleep = get_x(emp_id, j, ShiftType.SLEEP)

                            # 上界：两端必须都是睡觉班
                            model.Add(is_next_sleep <= current_is_sleep)
                            model.Add(is_next_sleep <= next_is_sleep)
                            
                            # 上界：中间不能再出现睡觉班
                            for k in range(i + 1, j):
                                model.Add(is_next_sleep <= 1 - get_x(emp_id, k, ShiftType.SLEEP))
                                
                            # 下界：两端是睡觉班且中间没有，就必须激活扣分
                            middle_clear = [1 - get_x(emp_id, k, ShiftType.SLEEP) for k in range(i + 1, j)]
                            req = [current_is_sleep, next_is_sleep] + middle_clear
                            model.Add(is_next_sleep >= sum(req) - (len(req) - 1))
                            
                            sleep_gap_penalty_terms.append(weight * is_next_sleep)        

        
        # Constraint 8: 尽量避免所有班次连续（软约束）
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

        # =======================================================
        # Constraint 9: 白班分配优先级（疲劳释放软约束）
        # 优先让刚上了夜班的人上白班。近期夜班越多，分配白班的奖励分越高。
        # 利用 get_x 完美支持跨月疲劳度的追溯！
        # =======================================================
        day_shift_rewards = []
        night_shifts = [ShiftType.SLEEP, ShiftType.MINI_NIGHT, ShiftType.LATE_NIGHT]

        for emp_id in self.emp_ids:
            if len(self.emp_ids) > 0 and emp_id == self.emp_ids[0]:  
                continue  # 排除第一名员工（他有专属的死规律）
                
            for i in range(len(self.work_days)):
                day_idx = i + self.num_prev_days
                is_day = x[emp_id, self.work_days[i], ShiftType.DAY]

                # 往前看 1 到 4 天，采用十进制级联权重，严格按夜班数量与连续性排名
                for lookback, weight in [(1, 1000), (2, 100), (3, 10), (4, 1)]:
                    if day_idx - lookback >= 0:
                        # 提取前几天是否上了夜班（支持跨月读取）
                        n_lookback = sum(get_x(emp_id, day_idx - lookback, s) for s in night_shifts)
                        
                        # 数学逻辑：只有当 “前几天上了夜班(n_lookback)” 且 “今天排了白班(is_day)” 都成立时，才触发奖励
                        and_var = model.NewBoolVar(f'day_reward_{emp_id}_{i}_{lookback}')
                        model.Add(and_var <= is_day)
                        model.Add(and_var <= n_lookback)
                        model.Add(and_var >= is_day + n_lookback - 1)
                        
                        day_shift_rewards.append(weight * and_var)
        
        # =======================================================
        # Constraint 10: 防止白班过于密集（终结“白-夜-白-夜-白”振荡现象）
        # 扫描跨月的任何连续 5 天窗口，如果白班达到 3 个，给予极其严厉的重罚
        # =======================================================
        dense_day_penalties = []
        for emp_id in self.emp_ids:
            if len(self.emp_ids) > 0 and emp_id == self.emp_ids[0]:
                continue  # 排除第一名员工
            
            # total_days 包含了上个月历史，所以这同样是一个无缝跨月的防密集校验
            for i in range(total_days - 4):
                # 获取这 5 天滑动窗口内的白班总数
                window_days_sum = sum(get_x(emp_id, i + j, ShiftType.DAY) for j in range(5))
                
                is_dense = model.NewBoolVar(f'dense_day_{emp_id}_{i}')
                # 核心逻辑：如果这 5 天里白班 >= 3 个，is_dense 就为 1（触发重罚）
                model.Add(window_days_sum >= 3).OnlyEnforceIf(is_dense)
                model.Add(window_days_sum < 3).OnlyEnforceIf(is_dense.Not())
                
                dense_day_penalties.append(is_dense)

        # =======================================================
        # Constraint 11: 休假回归后“孤立夜班”封杀令（五万分虚拟硬约束）
        # 规则：休假回来如果上了夜班，第二天必须也是夜班，坚决杜绝“只上1个夜班”
        # =======================================================
        isolated_night_penalties = []
        for emp_id in self.emp_ids:
            if len(self.emp_ids) > 0 and emp_id == self.emp_ids[0]:
                continue  # 排除第一名员工的死规律
                
            for i in range(len(self.work_days) - 1): 
                idx = i + self.num_prev_days
                if idx >= 1:
                    # 抓取连续三天的状态
                    yesterday_exempt = sum(get_x(emp_id, idx - 1, s) for s in exempt_shifts)
                    today_night = sum(get_x(emp_id, idx, s) for s in night_shifts)
                    tomorrow_night = sum(get_x(emp_id, idx + 1, s) for s in night_shifts)
                    
                    # 核心数学逻辑：如果昨天休假(1) + 今天夜班(1)，那么明天夜班必须为 1
                    # 如果明天没排夜班，is_violation 就会被迫变成 1，触发天价罚款
                    is_violation = model.NewBoolVar(f'isolated_night_{emp_id}_{i}')
                    model.Add(tomorrow_night + is_violation >= yesterday_exempt + today_night - 1)
                    
                    isolated_night_penalties.append(is_violation)        

        model.Minimize(
            consecutive_weight * sum(consecutive_penalties)
            + 50000 * sum(isolated_night_penalties) # <--- 新增：发现休假后只上1个夜班，重罚五万分！
            + 10000 * sum(min_gap_penalties)
            + 5000 * sum(max_gap_penalties)
            + sum(mini_gap_penalty_terms)           # 小夜班 1~8 天分层惩罚
            + 12000 * sum(mini_gap_gt_8_penalties) # 小夜班超过 8 天重罚
            + sum(sleep_gap_penalty_terms)         # <--- 新增：睡觉班间隔动态惩罚
            + variance_weight * sum(deviations)
            + 500 * sum(sleep_chief_3_penalties)
            + 2000 * sum(dense_day_penalties)
            + sum(random_terms)
            - sum(day_shift_rewards)
            # (之前的 - sum(post_vacation_night_rewards) 记得删掉)
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
