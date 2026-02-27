# 功能实现总结：冲突详情优化与单元格锁定

## 实现时间
2026-02-26

## 功能概述

本次更新实现了以下核心功能：

1. **冲突详情统一显示**：将冲突信息从单元格移至页面右下角统一展示
2. **一键优化功能**：根据排班规则自动优化当前排班
3. **一键回退功能**：回退到优化前的排班状态
4. **单元格锁定功能**：锁定特定单元格，防止被自动修改
5. **算法支持锁定**：智能排班和一键优化时考虑锁定的单元格

## 详细实现

### 1. 前端实现

#### 1.1 类型定义更新 (`web/types.ts`)

```typescript
export interface ShiftRecord {
  employeeId: string;
  date: string;
  type: ShiftType;
  label?: string;
  seatType?: string;
  isLocked?: boolean; // 新增：是否锁定
}
```

#### 1.2 App.tsx 核心功能

**新增状态**：
```typescript
const [lockedCells, setLockedCells] = useState<Set<string>>(new Set()); // 锁定的单元格
const [backupSchedules, setBackupSchedules] = useState<DailySchedule[] | null>(null); // 优化前的备份
```

**新增函数**：

1. **toggleCellLock** - 切换单元格锁定状态
   - 更新 `lockedCells` Set
   - 同步更新 `ShiftRecord.isLocked` 属性

2. **handleOptimizeSchedule** - 一键优化
   - 备份当前排班到 `backupSchedules`
   - 收集锁定的单元格数据
   - 调用后端 API 生成优化排班
   - 保留锁定单元格的原有数据

3. **handleUndoOptimize** - 回退优化
   - 恢复 `backupSchedules` 中的排班数据
   - 清空备份

**修改的函数**：

- **handleAutoScheduleAll** - 智能一键排班
  - 不再清空 `lockedCells`
  - 收集锁定单元格数据传递给后端
  - 合并返回结果时保留锁定单元格

#### 1.3 MatrixGrid 组件更新

**新增 Props**：
```typescript
lockedCells?: Set<string>;
onToggleCellLock?: (date: string, empId: string) => void;
```

**ShiftCell 组件更新**：
- 新增 `isLocked` 和 `onToggleLock` props
- 显示锁定/解锁图标
  - 锁定时：显示绿色锁定图标（左上角）
  - 未锁定时：hover 显示灰色解锁图标
- 移除冲突提示框（tooltip）相关代码
- 添加锁定状态的视觉反馈（绿色边框）

#### 1.4 MatrixFooter 组件更新

**新增 Props**：
```typescript
onOptimize?: () => void;
onUndoOptimize?: () => void;
canUndo?: boolean;
```

**新增功能**：
- 冲突数量显示改为可点击按钮
- 点击后弹出冲突详情弹窗
- 弹窗显示所有冲突的详细信息
- 提供"一键优化"和"回退优化"按钮

**冲突详情弹窗**：
- 全屏遮罩层
- 居中显示的卡片式弹窗
- 列表展示所有冲突
- 每个冲突显示：日期、班次类型、错误信息、涉及员工

### 2. 后端实现

#### 2.1 数据模型更新 (`backend/app/models/schemas.py`)

```python
class AutoGenerateRequest(BaseModel):
    month: str
    group_id: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    locked_records: Optional[list[dict]] = None  # 新增
```

#### 2.2 调度求解器更新 (`backend/app/services/scheduler.py`)

**SchedulingSolver.__init__ 新增参数**：
```python
locked_assignments: dict[tuple[str, str], ShiftType] | None = None
```

**新增约束（Constraint 7.65）**：
```python
# 锁定的单元格约束（硬约束）
for (emp_id, day), shift_type in self.locked_assignments.items():
    if emp_id in self.emp_ids and day in self.work_days:
        model.Add(x[emp_id, day, shift_type] == 1)
```

#### 2.3 API 路由更新 (`backend/app/routers/schedule.py`)

**auto_generate_schedule 函数更新**：
- 解析 `request.locked_records`
- 构建 `locked_assignments` 字典
- 传递给 `SchedulingSolver`

```python
locked_assignments = {}
if request.locked_records:
    for locked in request.locked_records:
        emp_id = str(locked.get('employee_id'))
        date = locked.get('date')
        shift_type_str = locked.get('shift_type')
        if emp_id and date and shift_type_str:
            try:
                shift_type = ShiftType(shift_type_str)
                locked_assignments[(emp_id, date)] = shift_type
            except ValueError:
                pass
```

#### 2.4 前端 API 更新 (`web/api.ts`)

```typescript
export interface AutoGenerateRequest {
  month: string;
  group_id: string;
  start_date?: string;
  end_date?: string;
  locked_records?: Array<{
    employee_id: number;
    date: string;
    shift_type: string;
  }>;
}
```

## 使用流程

### 锁定单元格
1. 鼠标悬停在单元格上
2. 点击左上角的解锁图标
3. 单元格显示绿色边框和锁定图标
4. 再次点击可解锁

### 一键优化
1. 点击页面右下角的冲突提示（红色警告框）
2. 查看冲突详情弹窗
3. 点击"一键优化"按钮
4. 系统自动优化排班，保留锁定的单元格
5. 如需回退，点击"回退优化"按钮

### 智能一键排班
1. 点击顶部的"智能一键排班"按钮
2. 系统生成全新排班，但保留锁定的单元格
3. 锁定的单元格不会被修改

## 技术要点

### 1. 锁定单元格的标识
- 使用 `${date}-${empId}` 作为唯一键
- 存储在 `Set<string>` 中，便于快速查找
- 同步更新到 `ShiftRecord.isLocked` 属性

### 2. 优化备份机制
- 使用 `backupSchedules` 存储优化前的完整排班
- 仅在点击"一键优化"时创建备份
- 回退时直接恢复备份数据

### 3. 锁定约束的实现
- 后端使用硬约束（Hard Constraint）
- 确保求解器必须满足锁定单元格的班次
- 优先级高于其他软约束

### 4. 数据同步
- 前端收集锁定单元格数据
- 转换为后端格式传递
- 后端返回结果后，前端合并锁定单元格

## 视觉设计

### 锁定状态
- **锁定**：绿色边框 + 绿色锁定图标（左上角）
- **未锁定**：hover 时显示灰色解锁图标

### 冲突提示
- **有冲突**：红色警告框，显示冲突数量，可点击
- **无冲突**：绿色成功框，显示"排班无冲突"

### 冲突详情弹窗
- 全屏半透明遮罩
- 白色卡片式弹窗（600px 宽）
- 红色主题的冲突列表
- 底部操作按钮：回退（灰色）+ 优化（蓝色）

## 测试建议

1. **锁定功能测试**
   - 锁定单元格后，点击"智能一键排班"，验证锁定单元格未被修改
   - 锁定单元格后，点击"一键优化"，验证锁定单元格未被修改
   - 解锁单元格，验证可以正常修改

2. **优化功能测试**
   - 创建冲突（如多个主任在同一夜班）
   - 点击冲突提示，查看详情
   - 点击"一键优化"，验证冲突被解决
   - 点击"回退优化"，验证恢复到优化前状态

3. **跨月切换测试**
   - 锁定单元格后切换月份，验证锁定状态被清空
   - 优化后切换月份，验证备份被清空

## 已知限制

1. 锁定状态不持久化，刷新页面后丢失
2. 优化备份仅保留一次，不支持多次回退
3. 锁定过多单元格可能导致求解器无解

## 未来改进方向

1. 锁定状态持久化到数据库
2. 支持多次回退（历史记录栈）
3. 优化无解时的友好提示
4. 批量锁定/解锁功能
5. 锁定单元格的视觉优化（更明显的标识）

## 文件清单

### 修改的文件
- `web/types.ts` - 添加 `isLocked` 字段
- `web/App.tsx` - 核心逻辑实现
- `web/components/MatrixGrid.tsx` - 锁定图标和交互
- `web/components/MatrixFooter.tsx` - 冲突详情弹窗
- `web/api.ts` - API 类型定义
- `backend/app/models/schemas.py` - 请求模型
- `backend/app/services/scheduler.py` - 锁定约束
- `backend/app/routers/schedule.py` - API 处理

### 新增的文件
- 无

## 总结

本次更新成功实现了冲突详情优化、一键优化、回退功能和单元格锁定功能。所有功能已完成前后端集成，算法能够正确处理锁定的单元格。用户体验得到显著提升，排班管理更加灵活和智能。
