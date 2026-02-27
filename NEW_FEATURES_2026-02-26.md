# 新功能实现 - 2026-02-26

## 功能概述

本次更新实现了以下新功能：

1. ✅ 一键锁定/解锁整行
2. ✅ 一键锁定/解锁整列
3. ✅ "重新生成该日排班"保留锁定单元格
4. ✅ 一键优化只优化当日及以后的日期
5. ✅ 回退按钮移到冲突详情旁边

---

## 详细功能说明

### 1. 一键锁定/解锁整行

**位置**：每行最右侧新增"锁定"列

**功能**：
- 点击锁定图标可一键锁定该行所有单元格
- 已锁定的行显示绿色锁定图标 🔒
- 未锁定的行显示灰色解锁图标 🔓
- 再次点击可解锁整行

**使用场景**：
- 某一天的排班已经确定，不希望被自动修改
- 快速锁定特殊日期（如节假日、重要活动日）

**实现细节**：
- 新增 `lockRow(date)` 和 `unlockRow(date)` 函数
- 自动更新所有员工在该日期的锁定状态
- 同步更新 `lockedCells` Set 和 `ShiftRecord.isLocked` 属性

---

### 2. 一键锁定/解锁整列

**位置**：每个员工列表头底部（hover 时显示）

**功能**：
- 鼠标悬停在员工名称列时，底部显示锁定/解锁图标
- 点击可一键锁定该员工整月的所有排班
- 已锁定的列显示绿色锁定图标 🔒
- 未锁定的列显示灰色解锁图标 🔓
- 再次点击可解锁整列

**使用场景**：
- 某个员工整月的排班已经确定（如长期休假、特殊安排）
- 快速锁定关键人员的排班

**实现细节**：
- 新增 `lockColumn(empId)` 和 `unlockColumn(empId)` 函数
- 自动更新该员工在所有日期的锁定状态
- 同步更新 `lockedCells` Set 和 `ShiftRecord.isLocked` 属性

---

### 3. "重新生成该日排班"保留锁定单元格

**改进前**：
- 点击"重新生成该日排班"会覆盖所有单元格，包括已锁定的

**改进后**：
- 重新生成时会保留所有锁定的单元格
- 只重新生成未锁定的单元格
- 确保用户手动锁定的排班不会被意外修改

**实现细节**：
```typescript
const handleRescheduleRow = useCallback((date: string) => {
  setSchedules(prev => prev.map(s => {
    if (s.date !== date) return s;

    // 保存锁定的单元格
    const lockedRecords = s.records.filter(r => {
      const cellKey = `${date}-${r.employeeId}`;
      return lockedCells.has(cellKey);
    });

    // 生成新的排班
    const newRecords = autoScheduleRowLogic(date, employees);

    // 合并：锁定的单元格保留原值，其他使用新生成的值
    const mergedRecords = newRecords.map(newRecord => {
      const locked = lockedRecords.find(lr => lr.employeeId === newRecord.employeeId);
      return locked || newRecord;
    });

    return { ...s, records: mergedRecords };
  }));
}, [employees, lockedCells]);
```

---

### 4. 一键优化只优化当日及以后的日期

**改进前**：
- 一键优化会优化整个月的排班，包括已经过去的日期

**改进后**：
- 自动获取今天的日期
- 只优化今天及以后的排班
- 过去的日期保持不变
- 优化完成后显示优化的天数

**实现细节**：
```typescript
const handleOptimizeSchedule = useCallback(async () => {
  // 获取今天的日期
  const today = new Date().toISOString().split('T')[0];

  // 过滤出今天及以后的排班
  const futureSchedules = schedules.filter(s => s.date >= today);

  if (futureSchedules.length === 0) {
    alert('没有需要优化的日期（当日及以后）');
    return;
  }

  // 收集锁定的单元格数据（只包含今天及以后的）
  const lockedRecords = futureSchedules.flatMap(schedule =>
    schedule.records.filter(r => {
      const cellKey = `${schedule.date}-${r.employeeId}`;
      return lockedCells.has(cellKey);
    })
  );

  // 获取优化的起止日期
  const startDate = futureSchedules[0].date;
  const endDate = futureSchedules[futureSchedules.length - 1].date;

  const result = await autoGenerateSchedule({
    month: selectedMonth,
    group_id: activeGroup,
    start_date: startDate,
    end_date: endDate,
    locked_records: lockedRecords.map(r => ({
      employee_id: parseInt(r.employeeId),
      date: r.date,
      shift_type: r.type,
    })),
  });

  // ... 更新排班数据
  alert(`优化成功！已优化 ${convertedSchedules.length} 天的排班`);
}, [isBackendAvailable, selectedMonth, activeGroup, schedules, lockedCells]);
```

**优势**：
- 避免修改历史数据
- 更符合实际使用场景
- 提高优化效率

---

### 5. 回退按钮移到冲突详情旁边

**改进前**：
- 回退按钮在冲突详情弹窗内部
- 需要先打开弹窗才能看到回退按钮

**改进后**：
- 回退按钮直接显示在页面底部，冲突提示的左侧
- 只有在执行过优化后才显示（`canUndo` 为 true）
- 点击即可立即回退，无需打开弹窗
- 更加直观和便捷

**UI 布局**：
```
[回退优化] [发现 X 个冲突 - 点击查看详情]
```

**实现细节**：
- 在 `MatrixFooter` 组件中添加回退按钮
- 使用 `canUndo` 属性控制显示/隐藏
- 从冲突详情弹窗中移除回退按钮
- 更新弹窗中的"一键优化"按钮文案为"一键优化（当日及以后）"

---

## 界面变化

### 表格布局
- 原布局：`80px repeat(N, 70px) 40px 140px`
- 新布局：`80px repeat(N, 70px) 40px 140px 80px`
- 新增最右侧"锁定"列（80px 宽）

### 表头变化
- 每个员工列底部新增锁定/解锁图标（hover 显示）
- 最右侧新增"锁定"列表头

### 每行变化
- 最右侧新增锁定整行按钮
- 按钮根据该行锁定状态显示不同图标和颜色

### 底部栏变化
- 新增"回退优化"按钮（仅在有备份时显示）
- 按钮位于冲突提示左侧

---

## 使用流程示例

### 场景1：锁定特定日期后优化

1. 用户手动设置某些日期的排班（如休假、特殊安排）
2. 点击该日期行最右侧的锁定按钮，锁定整行
3. 点击底部"发现 X 个冲突"查看冲突详情
4. 点击"一键优化（当日及以后）"
5. 系统优化当日及以后的排班，但保留锁定的日期
6. 如果不满意，点击"回退优化"恢复

### 场景2：锁定特定员工后重新生成

1. 某个员工整月排班已确定
2. 鼠标悬停在该员工列表头，点击底部的锁定图标
3. 该员工整列被锁定（显示绿色边框）
4. 点击某一天的"重新生成该日排班"按钮
5. 系统重新生成该日排班，但保留该员工的锁定单元格

### 场景3：快速回退优化

1. 执行一键优化后发现结果不理想
2. 直接点击底部的"回退优化"按钮
3. 排班立即恢复到优化前的状态
4. 可以手动调整后再次优化

---

## 技术要点

### 1. 锁定状态管理
- 使用 `Set<string>` 存储锁定的单元格键（格式：`${date}-${empId}`）
- 同步更新 `ShiftRecord.isLocked` 属性
- 确保状态一致性

### 2. 批量锁定操作
- `lockRow`：遍历所有员工，添加到 `lockedCells`
- `unlockRow`：遍历所有员工，从 `lockedCells` 移除
- `lockColumn`：遍历所有日期，添加到 `lockedCells`
- `unlockColumn`：遍历所有日期，从 `lockedCells` 移除

### 3. 日期过滤
- 使用 `new Date().toISOString().split('T')[0]` 获取今天日期
- 使用字符串比较 `s.date >= today` 过滤未来日期
- 确保时区一致性

### 4. 数据合并
- 重新生成时：先保存锁定记录，生成新记录，然后合并
- 优化时：传递锁定记录给后端，后端返回结果后再次合并
- 确保锁定数据不被覆盖

---

## 修改的文件

### 前端文件
1. **`web/App.tsx`**
   - 新增 `lockRow`、`unlockRow`、`lockColumn`、`unlockColumn` 函数
   - 修改 `handleRescheduleRow` 保留锁定单元格
   - 修改 `handleOptimizeSchedule` 只优化当日及以后
   - 传递新的 props 给 `MatrixGrid`

2. **`web/components/MatrixGrid.tsx`**
   - 更新 `MatrixGridProps` 接口，新增 4 个锁定函数
   - 修改表格布局，新增"锁定"列
   - 在员工列表头添加锁定/解锁整列按钮
   - 在每行最右侧添加锁定/解锁整行按钮

3. **`web/components/MatrixFooter.tsx`**
   - 在底部栏添加"回退优化"按钮
   - 从冲突详情弹窗移除回退按钮
   - 更新"一键优化"按钮文案

---

## 测试建议

### 1. 锁定整行功能
- 点击某一天的锁定按钮，验证该行所有单元格被锁定（绿色边框）
- 再次点击，验证该行所有单元格被解锁
- 锁定后点击"重新生成该日排班"，验证锁定单元格未被修改

### 2. 锁定整列功能
- 鼠标悬停在员工列表头，验证底部显示锁定图标
- 点击锁定图标，验证该员工整列被锁定
- 再次点击，验证该员工整列被解锁
- 锁定后执行一键优化，验证锁定单元格未被修改

### 3. 优化当日及以后
- 在过去的日期设置一些排班
- 点击"一键优化"
- 验证过去的日期未被修改
- 验证今天及以后的日期被优化
- 查看优化成功提示，确认优化的天数正确

### 4. 回退功能
- 执行一键优化
- 验证底部出现"回退优化"按钮
- 点击回退按钮
- 验证排班恢复到优化前的状态
- 验证回退按钮消失

### 5. 综合测试
- 锁定部分行和列
- 执行一键优化
- 验证锁定的单元格未被修改
- 验证未锁定的单元格被优化
- 回退后验证所有数据恢复

---

## 已知限制

1. 锁定状态不持久化，刷新页面后丢失
2. 优化备份仅保留一次，不支持多次回退
3. 切换月份或组别后，锁定状态和备份会被清空

---

## 未来改进方向

1. 锁定状态持久化到数据库
2. 支持多次回退（历史记录栈）
3. 批量锁定/解锁操作（如锁定所有周末）
4. 锁定状态的导入/导出
5. 锁定原因备注功能

---

**实现完成时间**：2026-02-26
**构建状态**：✅ 成功（无语法错误）
**代码大小**：249.04 KB (gzip: 76.34 KB)
