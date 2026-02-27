# 智能排班算法修复总结 - 2026-02-26

## 问题分析

### 原始问题
1. 第一列人员的"1白班+2睡觉班"规律每月重置，没有延续上个月
2. 主任白班连续过多，违反"间隔1至3个工作日"规则

### 修复尝试
1. ✅ 实现了第一列人员跨月延续逻辑
2. ✅ 将主任白班最小间隔改为软约束（高权重）
3. ❌ 遇到性能问题：求解器超时（>90秒）

## 根本原因

**性能瓶颈**：
- 原算法包含大量复杂的软约束（最大间隔约束）
- 每个约束都需要创建多个布尔变量和条件
- 对于30天×17人×4班次，变量数量爆炸

**约束冲突**：
- 主任白班：6人分3个白班位，每人平均15个白班/月
- 如果严格要求间隔1天（硬约束），数学上可行但求解困难
- 软约束权重不够高时，求解器会选择违反约束

## 当前状态

### 已实现的功能
1. ✅ 第一列人员跨月延续（代码已完成）
2. ✅ 锁定单元格支持（避免与固定规律冲突）
3. ✅ 主任白班连续惩罚（权重1000，与其他连续班次相同）

### 性能问题
- 10天排班：可以在30秒内完成
- 30天排班：超时（>90秒）

### 测试结果（10天）
```
第一个员工: DAY SLEEP SLEEP DAY SLEEP SLEEP DAY SLEEP SLEEP DAY
主任白班连续: 员工2-4有连续，员工5-6无连续
普通员工白班: 全部无连续（硬约束生效）
```

## 建议的解决方案

### 方案1：简化约束（推荐）
**优点**：快速可行
**缺点**：可能不完全符合业务规则

**具体措施**：
1. 移除所有最大间隔约束（软约束）
2. 只保留最小间隔约束（硬约束）
3. 主任白班最小间隔改为硬约束（可能导致无解）

### 方案2：分阶段求解
**优点**：可以处理复杂约束
**缺点**：实现复杂

**具体措施**：
1. 第一阶段：只考虑硬约束，快速生成可行解
2. 第二阶段：在可行解基础上，局部优化软约束
3. 使用启发式算法（如局部搜索）

### 方案3：放宽主任白班约束
**优点**：最简单，立即可用
**缺点**：主任白班可能连续

**具体措施**：
1. 保持主任白班最小间隔为软约束
2. 提高权重到2000或更高
3. 接受少量连续白班（业务妥协）

## 推荐实施方案

**短期（立即可用）**：
- 采用方案3：放宽主任白班约束
- 权重设置为2000（是其他软约束的4倍）
- 在前端显示警告：主任白班可能偶尔连续

**中期（1-2周）**：
- 采用方案1：简化约束
- 移除最大间隔约束
- 主任白班改为硬约束，如果无解则降级为软约束

**长期（1-2月）**：
- 采用方案2：分阶段求解
- 实现更智能的求解策略
- 支持用户自定义约束权重

## 代码修改记录

### 文件：`backend/app/services/scheduler.py`

**修改1：跨月延续（第132-160行）**
```python
# 新增属性
self.first_emp_last_shift: ShiftType | None = None

# 初始化逻辑
if self.previous_schedules:
    # 获取第一个员工上个月最后一天的班次
    if sorted_prev and len(self.emp_ids) > 0:
        first_emp_id = self.emp_ids[0]
        last_schedule = sorted_prev[-1]
        for record in last_schedule.records:
            if record.employee_id == first_emp_id:
                self.first_emp_last_shift = record.shift_type
                break
```

**修改2：第一列人员循环规律（第234-280行）**
```python
# 确定本月第一天应该在循环中的位置
start_offset = 0
if self.first_emp_last_shift is not None:
    if self.first_emp_last_shift == ShiftType.DAY:
        start_offset = 1  # 本月从睡觉班开始
    elif self.first_emp_last_shift == ShiftType.SLEEP:
        # 检查倒数第二天判断是第1个还是第2个睡觉班
        ...

# 应用循环规律，但要检查锁定单元格
for i, day in enumerate(self.work_days):
    if (first_emp_id, day) in self.locked_assignments:
        continue  # 跳过锁定的单元格

    cycle_pos = (i + start_offset) % 3
    if cycle_pos == 0:
        model.Add(x[first_emp_id, day, ShiftType.DAY] == 1)
    else:
        model.Add(x[first_emp_id, day, ShiftType.SLEEP] == 1)
```

**修改3：主任白班约束（第375-405行）**
```python
# 主任白班最小间隔（软约束，极高权重）
leader_day_consecutive_penalties = []
for i in range(len(self.work_days)):
    if i + 1 < len(self.work_days):
        consec_day = model.NewBoolVar(f"consec_day_{emp_id}_{i}")
        model.Add(
            x[emp_id, self.work_days[i], ShiftType.DAY] +
            x[emp_id, self.work_days[i + 1], ShiftType.DAY] >= 2
        ).OnlyEnforceIf(consec_day)
        model.Add(
            x[emp_id, self.work_days[i], ShiftType.DAY] +
            x[emp_id, self.work_days[i + 1], ShiftType.DAY] <= 1
        ).OnlyEnforceIf(consec_day.Not())
        leader_day_consecutive_penalties.append(consec_day)
```

**修改4：目标函数（第478-484行）**
```python
model.Minimize(
    consecutive_weight * sum(consecutive_penalties)
    + consecutive_weight * sum(leader_day_consecutive_penalties)  # 相同权重
    + 500 * sum(max_gap_penalties)
    + variance_weight * sum(deviations)
    + sum(random_terms)
)
```

**修改5：求解器超时（第486行）**
```python
solver.parameters.max_time_in_seconds = 60.0  # 从30秒增加到60秒
```

**修改6：简化约束（第342-344行）**
```python
# 暂时禁用大夜班最大间隔约束（性能优化）
# TODO: 重新启用并优化
```

## 测试建议

### 测试1：10天排班
```bash
cd backend
python test_scheduler.py
```
预期：30秒内完成，第一个员工规律正确

### 测试2：30天排班
```bash
# 修改 test_scheduler.py 中的 work_days 为30天
python test_scheduler.py
```
预期：60秒内完成（当前超时）

### 测试3：跨月延续
1. 生成2月排班（第一个员工最后一天是白班）
2. 生成3月排班
3. 验证3月第一天是睡觉班

## 下一步行动

1. **立即**：实施方案3，提高主任白班惩罚权重到2000
2. **本周**：优化求解器性能，确保30天排班在60秒内完成
3. **下周**：实施方案1，简化约束，测试主任白班硬约束
4. **下月**：如果性能仍有问题，考虑方案2（分阶段求解）

---

**修复时间**：2026-02-26
**状态**：部分完成（跨月延续✅，主任白班❌性能问题）
**需要重启后端**：是
