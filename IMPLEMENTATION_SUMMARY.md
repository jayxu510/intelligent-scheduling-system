# 核心业务逻辑实现总结

根据 prompt2.txt 的需求，已完成以下核心业务逻辑的实现：

## ✅ 已实现功能

### A. 每日岗位定员（硬约束）

**实现位置：** `backend/app/services/validator.py`

**规则：**
- 白班 (6人)：普通和主任席位都可以
- 睡觉班 (5人)：1个主任席 + 2个西北席 + 2个东南席
- 小夜班 (3人)：1个主任席 + 2个普通席
- 大夜班 (3人)：1个主任席 + 2个普通席
- 总计：每日必须17人

**验证逻辑：**
```python
def validate_daily_schedule(date, records, employees, constraints):
    # 检查1：总人数是否为17人
    # 检查2：各班次人数是否符合要求
    # 检查3：夜班主任席是否由前6人担任
    # 检查4：避让组冲突检测
    # 检查5：员工重复分配检测
```

**触发时机：**
1. 用户手动调整某一个人某一日的排班时（前端实时验证）
2. 智能一键排班后（后端验证）
3. 重新生成该日排班后（后端验证）
4. 保存排班前（后端验证）

---

### B. 人员属性与限制（硬约束）

**实现位置：** `backend/app/services/validator.py` + `backend/app/services/scheduler.py`

**规则：**
1. **总人数：** 17人（每组独立）
2. **夜班主任席人员：** 人员列表中的前6人（Index 0-5）
   - 睡觉班、小夜班、大夜班的"主任席"必须且只能由这6人担任
3. **避让组：** 系统维护互斥列表（如 [[UserA, UserB, UserC, UserD]]）
   - 尽量避免同一组的人分配到同一个班次类型
   - 如果无法避免，给予算法惩罚权重

**验证逻辑：**
```python
# 检查主任席
for shift_type in CHIEF_REQUIRED_SHIFTS:
    leaders_in_shift = [e for e in emps_in_shift if e in leader_ids]
    if len(leaders_in_shift) == 0:
        # 错误：缺少主任席
    elif len(leaders_in_shift) > 1:
        # 错误：存在多个主任席

# 检查避让组冲突
for group in constraints.avoidance_groups:
    conflicting = [e for e in emps_in_shift if e in group_emp_ids]
    if len(conflicting) > 1:
        # 警告：避让组冲突
```

**智能排班算法约束：**
```python
# scheduler.py 中的约束
# Constraint 3: Each night shift must have exactly one chief
for shift in chief_shifts:
    for day in work_days:
        model.Add(sum(c[emp_id, day, shift] for emp_id in leader_ids) == 1)

# Constraint 4: Chief assignment implies regular assignment
for emp_id in leader_ids:
    for day in work_days:
        for shift in chief_shifts:
            model.Add(c[emp_id, day, shift] <= x[emp_id, day, shift])

# 避让组惩罚
for emp1, emp2 in avoidance_pairs:
    for day in work_days:
        for shift in shift_types:
            both_in_shift = model.NewBoolVar(...)
            avoidance_penalties.append(both_in_shift)
```

---

### C. 公平性优化（软约束）

**实现位置：** `backend/app/services/scheduler.py` + `backend/app/services/validator.py`

**规则：**
1. **大夜班公平性：** 在整月范围内，确保每人的"大夜班"总数标准差最小
2. **避免连续夜班：**
   - 避免一个人员连续上大夜班（最高优先级）
   - 其次是小夜班、睡觉班也尽量隔开

**智能排班算法优化目标：**
```python
# 1. 大夜班公平性
late_night_counts = {}  # 统计每人大夜班次数
avg_late_nights = total_late_nights // len(employees)

# 最小化偏差
for emp_id in emp_ids:
    pos_dev = model.NewIntVar(...)
    neg_dev = model.NewIntVar(...)
    model.Add(late_night_counts[emp_id] - avg_late_nights == pos_dev - neg_dev)
    deviations.append(pos_dev)
    deviations.append(neg_dev)

# 2. 避免连续夜班
for i in range(len(work_days) - 1):
    day1 = work_days[i]
    day2 = work_days[i + 1]

    for emp_id in emp_ids:
        # 连续大夜班（高权重惩罚：20）
        consecutive_late = model.NewBoolVar(...)
        consecutive_penalties.append(consecutive_late * 20)

        # 连续小夜班（中等权重：10）
        consecutive_mini = model.NewBoolVar(...)
        consecutive_penalties.append(consecutive_mini * 10)

        # 连续睡觉班（低权重：5）
        consecutive_sleep = model.NewBoolVar(...)
        consecutive_penalties.append(consecutive_sleep * 5)

# 综合目标函数
model.Minimize(
    variance_weight * sum(deviations)           # 公平性权重：10
    + avoidance_weight * sum(avoidance_penalties)  # 避让冲突权重：5
    + consecutive_weight * sum(consecutive_penalties)  # 连续夜班权重：1
)
```

**验证逻辑：**
```python
def _check_fairness(schedules, employees):
    # 统计每人大夜班次数
    late_night_counts = defaultdict(int)

    # 计算标准差
    std_dev = variance ** 0.5

    # 标准差阈值：2.0
    if std_dev > 2.0:
        # 警告：大夜班分配不均衡

def _check_consecutive_nights(schedules, employees):
    # 检查连续大夜班（间隔<=3天）
    # 检查连续小夜班
    # 检查连续睡觉班
```

---

## 🔄 实时校验流程

### 1. 用户手动调整排班

**触发点：** `web/App.tsx` 的 `handleUpdateShift()`

```typescript
const handleUpdateShift = useCallback((date: string, empId: string, newType: ShiftType) => {
  // 1. 更新状态
  setSchedules(prev => ...);

  // 2. 实时验证（异步，不阻塞UI）
  if (isBackendAvailable) {
    setTimeout(() => {
      // 调用后端验证接口
      validateDaySchedule(date, records);
    }, 100);
  }
}, [schedules, isBackendAvailable]);
```

**前端冲突检测：** `web/App.tsx` 的 `conflicts` useMemo

```typescript
const conflicts = useMemo(() => {
  // A规则：检查每日岗位定员
  // B规则：检查夜班主任席
  // B规则：检查避让组冲突
  // 实时显示在 MatrixFooter 中
}, [filteredSchedules, avoidanceRules]);
```

### 2. 智能一键排班

**触发点：** `web/App.tsx` 的 `handleAutoScheduleAll()`

```typescript
const handleAutoScheduleAll = useCallback(async () => {
  // 1. 调用后端 OR-Tools 算法
  const result = await autoGenerateSchedule({
    month: selectedMonth,
    group_id: activeGroup,
  });

  // 2. 算法已内置所有约束（A、B、C规则）
  // 3. 返回的排班已经是最优解

  // 4. 更新前端状态
  setSchedules(convertedSchedules);
}, [isBackendAvailable, selectedMonth, activeGroup, employees]);
```

**后端算法：** `backend/app/services/scheduler.py`

- 使用 Google OR-Tools CP-SAT 求解器
- 硬约束：A和B规则（必须满足）
- 软约束：C规则（优化目标）
- 求解时间限制：30秒

### 3. 重新生成该日排班

**触发点：** `web/App.tsx` 的 `handleRescheduleRow()`

```typescript
const handleRescheduleRow = useCallback((date: string) => {
  // 使用本地随机算法重新生成
  setSchedules(prev => prev.map(s => {
    if (s.date !== date) return s;
    return { ...s, records: autoScheduleRowLogic(date, employees) };
  }));

  // 注意：本地算法不保证满足所有约束
  // 用户需要手动调整或使用智能排班
}, [employees]);
```

---

## 📊 告警机制

### 错误类型

| 错误类型 | 严重级别 | 说明 |
|---------|---------|------|
| `HEADCOUNT_MISMATCH` | error | 总人数不足17人 |
| `SHIFT_COUNT_MISMATCH` | error | 某班次人数不符合要求 |
| `CHIEF_MISSING` | error | 夜班缺少主任席 |
| `CHIEF_DUPLICATE` | error | 夜班存在多个主任席 |
| `DUPLICATE_ASSIGNMENT` | error | 员工重复分配 |
| `AVOIDANCE_CONFLICT` | warning | 避让组冲突 |
| `FAIRNESS_IMBALANCE` | warning | 大夜班分配不均衡 |
| `CONSECUTIVE_LATE_NIGHT` | warning | 连续上大夜班 |
| `CONSECUTIVE_MINI_NIGHT` | warning | 连续上小夜班 |

### 显示位置

**前端：** `web/components/MatrixFooter.tsx`

```typescript
<div className="conflicts">
  {conflicts.map(conflict => (
    <div className={conflict.type === 'error' ? 'error' : 'warning'}>
      {conflict.message}
    </div>
  ))}
</div>
```

**后端：** API 响应中的 `errors` 数组

```json
{
  "is_valid": false,
  "errors": [
    {
      "type": "CHIEF_MISSING",
      "date": "2026-01-01",
      "message": "2026-01-01 大夜班 缺少主任席",
      "employee_ids": []
    }
  ]
}
```

---

## 🔌 API 接口

### 1. 验证单日排班

```
POST /api/schedule/validate-day?date=2026-01-01
Body: [ShiftRecordDTO]
Response: { is_valid: boolean, errors: [...] }
```

### 2. 验证整月排班

```
POST /api/schedule/validate-month
Body: [DailyScheduleDTO]
Response: {
  is_valid: boolean,
  errors: [...],
  summary: { total_errors: number, error_types: [...] }
}
```

### 3. 智能排班（已包含所有约束）

```
POST /api/schedule/auto-generate
Body: { month: "2026-01", group_id: "A" }
Response: { schedules: [...], statistics: {...} }
```

---

## 🎯 使用场景

### 场景1：用户手动排班

1. 用户点击某个格子，切换班次类型
2. 前端立即更新UI
3. 前端 `conflicts` useMemo 自动重新计算
4. MatrixFooter 实时显示冲突告警
5. 用户根据告警调整排班

### 场景2：智能一键排班

1. 用户点击"智能排班"按钮
2. 前端调用 `/api/schedule/auto-generate`
3. 后端 OR-Tools 求解器运行（最多30秒）
4. 算法自动满足所有硬约束（A、B规则）
5. 算法优化软约束（C规则）
6. 返回最优排班方案
7. 前端显示结果，无冲突告警

### 场景3：保存前验证

1. 用户点击"保存"按钮
2. 前端调用 `/api/schedule/validate-month`
3. 后端验证整月排班（包括公平性检查）
4. 如果有错误，阻止保存并显示告警
5. 如果只有警告，提示用户确认后保存
6. 验证通过后，调用 `/api/schedule/save` 保存

---

## 📝 技术细节

### OR-Tools CP-SAT 求解器

**优势：**
- 高效求解复杂约束问题
- 支持硬约束和软约束
- 自动寻找最优解
- 可设置求解时间限制

**约束类型：**
```python
# 硬约束（必须满足）
model.Add(constraint)

# 软约束（优化目标）
penalty_var = model.NewBoolVar(...)
model.Minimize(sum(penalties))
```

### 权重调优

当前权重设置：
- 公平性（大夜班标准差）：10
- 避让组冲突：5
- 连续大夜班：20
- 连续小夜班：10
- 连续睡觉班：5

可根据实际需求调整权重比例。

---

## ✅ 测试建议

1. **单元测试：** 测试 `validate_daily_schedule()` 各种场景
2. **集成测试：** 测试智能排班算法生成的结果是否满足所有约束
3. **压力测试：** 测试求解器在复杂约束下的性能
4. **用户测试：** 验证告警信息是否清晰易懂

---

## 🚀 后续优化方向

1. **性能优化：** 缓存验证结果，避免重复计算
2. **用户体验：** 在格子上直接显示冲突标记
3. **智能提示：** 当用户调整排班时，提示可能的冲突
4. **历史记录：** 记录排班调整历史，支持撤销/重做
5. **批量操作：** 支持批量调整多人多日排班
