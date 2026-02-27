# 智能排班算法优化说明

## 优化概述

基于 Gemini 提供的算法建议，对项目核心排班算法进行了以下关键优化：

## 主要改进

### 1. 跨月公平性优化（规则4和6）

**问题**：原算法仅考虑当月班次分配的公平性，无法保证连续两个月的整体平衡。

**解决方案**：
- 在求解器初始化时，统计上个月每个员工的各班次数量
- 目标函数中使用"本月班次数 + 上月班次数"作为公平性计算依据
- 最小化两个月累计班次的最大值与最小值之差（spread）

**代码实现**：
```python
# 构建历史班次统计
self.prev_shift_counts: dict[str, dict[ShiftType, int]] = defaultdict(lambda: defaultdict(int))

# 在目标函数中考虑两个月总数
total_cnt = model.NewIntVar(0, len(self.work_days) * 2, f"staff_{emp_id}_{shift.value}_total")
model.Add(total_cnt == current_cnt + prev_cnt)
```

**效果**：
- 确保员工在连续两个月内的班次分配更加均衡
- 避免某个员工本月排班过多或过少的情况
- 符合业务规则："每个人员连续两个月的每个班次尽量要平均"

### 2. 增强的统计信息

**新增统计指标**：
- `two_month_distributions`: 两个月累计的班次分布统计
- `two_month_employee_counts`: 每个员工两个月的班次总数
- `fairness_score`: 公平性评分（所有班次类型的spread总和，越低越好）
- `has_previous_data`: 是否有上个月的历史数据

**用途**：
- 前端可以展示两个月的公平性对比
- 管理员可以直观看到长期班次分配是否均衡
- 便于调整和优化排班策略

### 3. 算法文档完善

在 `scheduler.py` 文件头部添加了详细的算法设计文档，包括：
- 核心方法说明
- 关键特性列表
- 约束优先级说明
- 业务规则映射

## 算法核心特性

### 已实现的约束（基于 Gemini 建议）

| 约束类型 | 实现方式 | 权重 | 说明 |
|---------|---------|------|------|
| 第一列固定规律 | 硬约束 | - | 1白班+2睡觉班循环 |
| 大夜班最小间隔 | 硬约束 | - | 主任3-5天，普通3-6天 |
| 白班最小间隔 | 软约束（主任）<br>硬约束（普通） | 500 | 避免连续白班 |
| 连续班次避免 | 软约束 | 1000 | 最高优先级惩罚 |
| 最大间隔 | 软约束 | 500 | 避免间隔过大 |
| 公平性 | 软约束 | 200 | 两个月累计平衡 |
| 避让规则 | 硬约束 | - | 避让组成员不同班 |

### 求解器配置

```python
solver.parameters.max_time_in_seconds = 30.0  # 30秒超时
solver.parameters.random_seed = random.randint(0, 2**31 - 1)  # 随机种子，每次生成不同方案
```

## 与 Gemini 建议的对比

| Gemini 建议 | 实现状态 | 说明 |
|------------|---------|------|
| 使用 OR-Tools CP-SAT | ✅ 已实现 | 核心求解器 |
| 历史数据考虑 | ✅ 已优化 | 新增跨月公平性 |
| 间隔约束 | ✅ 已实现 | 最小/最大间隔 |
| 第一列固定规律 | ✅ 已实现 | 硬约束保证 |
| 软约束处理 | ✅ 已实现 | 惩罚机制 |
| 公平性目标 | ✅ 已优化 | 两个月spread最小化 |
| 手动修改建议 | 🔄 待实现 | 前端交互功能 |

## 使用示例

### API 调用

```bash
POST /api/schedule/auto-generate
{
  "month": "2024-11",
  "group_id": "A"
}
```

### 响应示例

```json
{
  "statistics": {
    "total_work_days": 10,
    "shift_distributions": {
      "DAY": {"min": 5, "max": 7, "avg": 6.0, "std_dev": 0.8, "spread": 2},
      "LATE_NIGHT": {"min": 2, "max": 3, "avg": 2.5, "std_dev": 0.5, "spread": 1}
    },
    "two_month_distributions": {
      "DAY": {"min": 11, "max": 13, "avg": 12.0, "std_dev": 0.7, "spread": 2},
      "LATE_NIGHT": {"min": 4, "max": 6, "avg": 5.0, "std_dev": 0.6, "spread": 2}
    },
    "fairness_score": 8,
    "has_previous_data": true
  }
}
```

## 性能优化

1. **求解时间**：30秒超时保证响应速度
2. **随机种子**：每次生成不同方案，避免重复
3. **约束分层**：硬约束保证可行性，软约束优化质量
4. **分组优化**：主任和普通员工分别计算公平性

## 未来改进方向

1. **智能建议功能**：当用户手动修改某个班次时，算法给出优化建议
2. **多目标优化**：支持用户自定义权重（公平性 vs 连续性 vs 间隔）
3. **增量求解**：仅重新计算受影响的日期范围
4. **历史趋势分析**：展示3个月以上的长期公平性趋势

## 技术栈

- **OR-Tools 9.x**: Google 约束规划求解器
- **Python 3.10+**: 后端语言
- **FastAPI**: Web 框架
- **CP-SAT Solver**: 约束满足问题求解器

## 参考资料

- Google OR-Tools 官方文档: https://developers.google.com/optimization
- CP-SAT Solver 指南: https://github.com/google/or-tools/blob/stable/ortools/sat/doc/README.md
- Gemini 算法建议文档: `prompt4.txt`
