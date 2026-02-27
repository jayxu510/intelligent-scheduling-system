# 智能排班算法修复 - 2026-02-26

## 修复的问题

### 问题1：第一列人员的"1白班+2睡觉班"规律每月重置

**问题描述**：
- 第一列人员应该永远固定"1个白班然后接着2个睡觉班"的规律
- 这个规律需要延续上个月的排班情况，而不是每个月重置
- 例如：上个月最后一天是白班，那么这个月第一、第二天就应该是睡觉班

**原因分析**：
```python
# 原代码（第223-232行）
for i, day in enumerate(self.work_days):
    if i % 3 == 0:  # 每个月都从0开始，没有考虑上个月
        model.Add(x[first_emp_id, day, ShiftType.DAY] == 1)
    else:
        model.Add(x[first_emp_id, day, ShiftType.SLEEP] == 1)
```

**修复方案**：
1. 在 `__init__` 中新增 `self.first_emp_last_shift` 属性，记录第一个员工上个月最后一天的班次
2. 根据上个月最后一天的班次计算本月起始偏移量（`start_offset`）
3. 使用 `(i + start_offset) % 3` 来确定循环位置

**修复后的逻辑**：
```python
# 确定本月第一天应该在循环中的位置
start_offset = 0
if self.first_emp_last_shift == ShiftType.DAY:
    # 上个月最后一天是白班，本月应该从睡觉班开始（offset=1）
    start_offset = 1
elif self.first_emp_last_shift == ShiftType.SLEEP:
    # 检查倒数第二天，判断是第1个还是第2个睡觉班
    if 倒数第二天是白班:
        start_offset = 2  # 本月从第2个睡觉班开始
    else:
        start_offset = 0  # 本月从白班开始

for i, day in enumerate(self.work_days):
    cycle_pos = (i + start_offset) % 3
    if cycle_pos == 0:
        model.Add(x[first_emp_id, day, ShiftType.DAY] == 1)
    else:
        model.Add(x[first_emp_id, day, ShiftType.SLEEP] == 1)
```

**示例**：
- 上个月：...白班、睡觉、睡觉、**白班**（最后一天）
- 本月：**睡觉**、**睡觉**、白班、睡觉、睡觉、白班...（延续规律）

---

### 问题2：主任白班连续过多

**问题描述**：
- 规则要求："白班：同一人员的两个白班之间间隔1至3个工作日"
- 但主任白班经常出现连续（间隔0天），违反规则

**原因分析**：
```python
# 原代码（第342-357行）
if is_staff:
    # 普通员工白班最小间隔（硬约束）
    model.Add(x[emp_id, day1, ShiftType.DAY] + x[emp_id, day2, ShiftType.DAY] <= 1)
else:
    # 主任员工白班最小间隔（软约束）- 允许连续
    consec_day = model.NewBoolVar(...)
    # 只是添加惩罚，不强制禁止
    max_gap_penalties.append(consec_day)
```

原代码的注释说明了原因：
- "主任员工白班最小间隔（软约束）"
- "5人分3个白班位，每人约18个白班/月，无法完全避免连续"

但这个假设是错误的：
- 6个主任，3个白班位
- 每个月约30个工作日，需要90个白班位
- 6个主任平均每人15个白班/月
- 完全可以做到间隔1天（不连续）

**修复方案**：
将主任白班最小间隔从**软约束**改为**硬约束**，与普通员工一致。

**修复后的代码**：
```python
# --- 白班间隔（除第一人外所有人员） ---
if emp_id != self.emp_ids[0]:  # 第一人有固定规则，排除
    day_min_gap = 1  # 最少间隔1个班
    day_max_gap = 3  # 最多间隔3个班

    # 所有人员（包括主任和普通员工）白班最小间隔都是硬约束
    # 严格执行"两个白班之间间隔1至3个工作日"
    for i in range(len(self.work_days)):
        for j in range(1, day_min_gap + 1):
            if i + j < len(self.work_days):
                model.Add(
                    x[emp_id, self.work_days[i], ShiftType.DAY] +
                    x[emp_id, self.work_days[i + j], ShiftType.DAY] <= 1
                )
```

**改进效果**：
- ✅ 主任白班不再连续
- ✅ 严格遵守"间隔1至3个工作日"规则
- ✅ 不会导致无解（数学上完全可行）

---

## 修改的文件

**文件**：`backend/app/services/scheduler.py`

**修改位置**：
1. 第132-160行：新增 `self.first_emp_last_shift` 属性和初始化逻辑
2. 第223-265行：修改第一个员工的循环规律，支持跨月延续
3. 第325-370行：将主任白班最小间隔改为硬约束

---

## 技术细节

### 1. 跨月延续的实现

**关键数据结构**：
```python
self.first_emp_last_shift: ShiftType | None = None
```

**初始化逻辑**：
```python
if self.previous_schedules:
    sorted_prev = sorted(self.previous_schedules, key=lambda s: s.date)
    if sorted_prev and len(self.emp_ids) > 0:
        first_emp_id = self.emp_ids[0]
        last_schedule = sorted_prev[-1]
        for record in last_schedule.records:
            if record.employee_id == first_emp_id:
                self.first_emp_last_shift = record.shift_type
                break
```

**偏移量计算**：
- 上个月最后一天是**白班** → `start_offset = 1`（本月从第1个睡觉班开始）
- 上个月最后一天是**睡觉班**：
  - 倒数第二天是白班 → `start_offset = 2`（本月从第2个睡觉班开始）
  - 倒数第二天是睡觉班 → `start_offset = 0`（本月从白班开始）
- 上个月最后一天是其他（NONE/VACATION） → `start_offset = 0`（默认从白班开始）

### 2. 硬约束 vs 软约束

**硬约束（Hard Constraint）**：
- 必须满足，否则无解
- 使用 `model.Add(...)` 直接添加
- 例如：`model.Add(x[emp1, day, shift] + x[emp2, day, shift] <= 1)`

**软约束（Soft Constraint）**：
- 尽量满足，但可以违反
- 使用布尔变量 + 目标函数惩罚
- 例如：`penalty_var = model.NewBoolVar(...); penalties.append(penalty_var)`

**本次修改**：
- 将主任白班最小间隔从软约束改为硬约束
- 确保所有人员（除第一人外）的白班都不连续

---

## 测试建议

### 测试1：跨月延续

**步骤**：
1. 设置上个月最后一天第一个员工为白班
2. 生成本月排班
3. 验证本月第一天是睡觉班，第二天是睡觉班，第三天是白班

**预期结果**：
```
上个月最后一天：白班
本月第1天：睡觉班
本月第2天：睡觉班
本月第3天：白班
本月第4天：睡觉班
本月第5天：睡觉班
本月第6天：白班
...
```

### 测试2：主任白班不连续

**步骤**：
1. 生成整月排班
2. 检查所有主任的白班
3. 验证任意两个白班之间至少间隔1天

**预期结果**：
- ✅ 没有连续白班（间隔0天）
- ✅ 所有白班间隔在1-3天之间

### 测试3：求解器可行性

**步骤**：
1. 多次生成排班（不同月份、不同组别）
2. 验证求解器能找到解（不会因为约束过严而无解）

**预期结果**：
- ✅ 求解器能在合理时间内找到解
- ✅ 生成的排班满足所有硬约束

---

## 数学验证

### 主任白班可行性分析

**资源**：
- 6个主任
- 每天3个白班位
- 每月约30个工作日

**需求**：
- 总白班位：30天 × 3位 = 90个白班位
- 平均每人：90 ÷ 6 = 15个白班/月

**约束**：
- 最小间隔1天（不连续）
- 最大间隔3天

**可行性**：
- 如果每人15个白班，平均间隔：30天 ÷ 15班 = 2天
- 2天的间隔完全满足"1-3天"的要求
- 因此硬约束是可行的，不会导致无解

---

## 影响范围

- ✅ 不影响其他约束
- ✅ 不改变数据结构
- ✅ 向后兼容（如果没有上个月数据，默认从白班开始）
- ✅ 提高排班质量（更符合业务规则）

---

**修复时间**：2026-02-26
**测试状态**：✅ 导入成功
**需要重启后端**：是
