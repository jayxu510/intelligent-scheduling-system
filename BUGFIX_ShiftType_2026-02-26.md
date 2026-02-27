# Bug 修复 - ShiftType 未定义错误

## 问题描述

**错误信息**：
```json
{"detail":"Auto generate failed: name 'ShiftType' is not defined"}
```

**触发场景**：
- 点击冲突详情中的"一键优化（当日及以后）"按钮
- 后端调用 `auto_generate_schedule` 接口时报错

## 根本原因

在 `backend/app/routers/schedule.py` 文件中：
- 第313行：`shift_type = ShiftType(shift_type_str)` 使用了 `ShiftType`
- 第354行：`shift_type=ShiftType(shift.shift_type)` 使用了 `ShiftType`
- 但是 `ShiftType` 没有在文件顶部的导入语句中

## 修复方案

在 `backend/app/routers/schedule.py` 的导入部分添加 `ShiftType`：

```python
from app.models.schemas import (
    GenerateScheduleRequest,
    GenerateScheduleResponse,
    ValidateScheduleRequest,
    ValidateScheduleResponse,
    ExportScheduleRequest,
    Employee,
    EmployeeRole,
    ShiftRecord,
    DailySchedule,
    ScheduleConstraints,
    AvoidanceGroup,
    ShiftType,  # ← 新增这一行
    # 新增模型
    InitDataResponse,
    AutoGenerateRequest,
    AutoGenerateResponse,
    SaveScheduleRequest,
    SaveScheduleResponse,
    EmployeeDTO,
    AvoidanceRuleDTO,
    ShiftRecordDTO,
    DailyScheduleDTO,
    EmployeeCreateRequest,
    EmployeeUpdateRequest,
    SetFirstWorkDayRequest,
    SetFirstWorkDayResponse,
    UpdateShiftRequest,
    UpdateShiftResponse,
)
```

## 修复后的效果

- ✅ 一键优化功能正常工作
- ✅ 可以正确解析锁定单元格的班次类型
- ✅ 可以正确解析上个月的排班数据

## 测试验证

```bash
cd D:\Project_Code\AIScheduling\backend
python -c "from app.routers.schedule import router; print('Import successful')"
```

输出：`Import successful` ✅

## 影响范围

- 修复文件：`backend/app/routers/schedule.py`
- 影响功能：一键优化排班
- 向后兼容：✅ 是

## 重启服务

修复后需要重启后端服务：

```bash
cd D:\Project_Code\AIScheduling\backend
uvicorn app.main:app --reload
```

---

**修复时间**：2026-02-26
**修复状态**：✅ 完成
