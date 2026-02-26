
import React, { useState, useMemo, useCallback, useEffect } from 'react';
import { generateMonthSchedules, autoScheduleRowLogic } from './data';
import { ShiftType, DailySchedule, Conflict, Employee, ShiftRecord, EmployeeRole, AvoidanceRule, ConflictSuggestion } from './types';
import { generateConflictSuggestion } from './conflictResolver';
import MatrixHeader from './components/MatrixHeader';
import MatrixGrid from './components/MatrixGrid';
import MatrixFooter from './components/MatrixFooter';
import {
  fetchInitData,
  autoGenerateSchedule,
  saveSchedule,
  updateShift,
  downloadExcel,
  createEmployee as apiCreateEmployee,
  updateEmployee as apiUpdateEmployee,
  deleteEmployee as apiDeleteEmployee,
  checkHealth,
  setFirstWorkDay,
  EmployeeDTO,
  DailyScheduleDTO,
  ShiftRecordDTO,
} from './api';

// 数据转换函数：后端DTO -> 前端类型
const convertEmployeeFromDTO = (dto: EmployeeDTO): Employee => ({
  id: dto.id.toString(),
  name: dto.name,
  role: dto.is_night_leader ? EmployeeRole.LEADER : EmployeeRole.STAFF,
  title: dto.is_night_leader ? '夜班长' : undefined,
  avoidanceGroupId: dto.avoidance_group_id?.toString(),
  sequenceOrder: dto.sequence_order,
});

const convertScheduleFromDTO = (dto: DailyScheduleDTO): DailySchedule => ({
  date: dto.date,
  dayOfWeek: dto.day_of_week,
  records: dto.records.map(r => ({
    employeeId: r.employee_id.toString(),
    date: r.date,
    type: r.shift_type as ShiftType,
    seatType: r.seat_type || undefined,
    label: r.label || undefined,
  })),
});

// 数据转换函数：前端类型 -> 后端DTO
const convertScheduleToDTO = (schedule: DailySchedule): DailyScheduleDTO => ({
  date: schedule.date,
  day_of_week: schedule.dayOfWeek,
  records: schedule.records.map(r => ({
    employee_id: parseInt(r.employeeId),
    date: r.date,
    shift_type: r.type,
    seat_type: r.seatType || null,
    label: r.label || null,
  })),
});

const App: React.FC = () => {
  const [activeGroup, setActiveGroup] = useState<'A' | 'B' | 'C'>('A');
  const [selectedMonth, setSelectedMonth] = useState(() => {
    const now = new Date();
    const y = now.getFullYear();
    const m = (now.getMonth() + 1).toString().padStart(2, '0');
    return `${y}-${m}`;
  });
  const [employees, setEmployees] = useState<Employee[]>([]); // 从后端加载，不使用静态数据
  const [schedules, setSchedules] = useState<DailySchedule[]>([]);
  const [workDays, setWorkDays] = useState<string[]>([]);
  const [avoidanceRules, setAvoidanceRules] = useState<AvoidanceRule[]>([]);
  const [lockedCells, setLockedCells] = useState<Set<string>>(new Set()); // 用户手动修改过的单元格
  const [isLoading, setIsLoading] = useState(false);
  const [isBackendAvailable, setIsBackendAvailable] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [showWorkDaySelector, setShowWorkDaySelector] = useState(false);

  const [year, month] = useMemo(() => {
    const parts = selectedMonth.split('-');
    return [parseInt(parts[0]), parseInt(parts[1]) - 1];
  }, [selectedMonth]);

  // 检查后端服务状态
  useEffect(() => {
    const checkBackend = async () => {
      try {
        const health = await checkHealth();
        setIsBackendAvailable(health.status === 'healthy');
        console.log('Backend status:', health);
      } catch (err) {
        console.warn('Backend not available, using local mode');
        setIsBackendAvailable(false);
      }
    };
    checkBackend();
  }, []);

  // 从后端加载初始数据
  const loadInitData = useCallback(async () => {
    if (!isBackendAvailable) {
      // 后端不可用时使用本地空数据
      console.warn('Backend not available - no employee data loaded');
      setEmployees([]);
      setSchedules([]);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const data = await fetchInitData(selectedMonth, activeGroup);

      // 转换员工数据
      const convertedEmployees = data.employees.map(convertEmployeeFromDTO);
      setEmployees(convertedEmployees);

      // 转换排班数据
      const convertedSchedules = data.schedules.map(convertScheduleFromDTO);
      setSchedules(convertedSchedules);

      // 设置工作日
      setWorkDays(data.work_days);

      // 判断是否需要显示工作日选择器
      // 当工作日列表为空时，显示选择器
      setShowWorkDaySelector(data.work_days.length === 0);

      // 设置避让规则
      setAvoidanceRules(data.avoidance_rules.map(r => ({
        id: r.id.toString(),
        name: r.name || undefined,
        memberIds: r.member_ids.map(id => id.toString()),
        description: r.description || undefined,
      })));

      console.log('Data loaded from backend:', {
        employees: convertedEmployees.length,
        schedules: convertedSchedules.length,
        workDays: data.work_days.length,
      });
    } catch (err) {
      console.error('Failed to load init data:', err);
      setError('加载数据失败，请检查后端服务');
      // 清空数据，但显示工作日选择器
      setEmployees([]);
      setSchedules([]);
      setWorkDays([]);
      setShowWorkDaySelector(true); // 👈 关键修改：失败时也显示选择器
    } finally {
      setIsLoading(false);
    }
  }, [isBackendAvailable, selectedMonth, activeGroup, year, month]);

  // 月份或组别变化时重新加载数据
  useEffect(() => {
    loadInitData();
    setLockedCells(new Set()); // 切换月份/组别时清空锁定
  }, [selectedMonth, activeGroup, isBackendAvailable]);

  // 设置首个工作日
  const handleSetFirstWorkDay = useCallback(async (firstWorkDay: number) => {
    if (!isBackendAvailable) {
      alert('后端服务不可用，无法设置工作日');
      return;
    }

    if (!firstWorkDay || firstWorkDay < 1) {
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const result = await setFirstWorkDay({
        month: selectedMonth,
        group_id: activeGroup,
        first_work_day: firstWorkDay,
      });

      if (result.success) {
        console.log('工作日设置成功:', result.work_days);

        // 重新加载数据以获取新的工作日列表
        await loadInitData();

        alert(`设置成功！本月共有 ${result.work_days.length} 个工作日`);
      } else {
        throw new Error(result.message);
      }
    } catch (err) {
      console.error('设置首个工作日失败:', err);
      setError('设置工作日失败');
      alert('设置失败，请重试');
    } finally {
      setIsLoading(false);
    }
  }, [isBackendAvailable, selectedMonth, activeGroup, loadInitData]);

  // 辅助函数：获取班次中文名称（定义在 conflicts 之前）
  const getShiftName = useCallback((shiftType: ShiftType): string => {
    const names = {
      [ShiftType.DAY]: '白班',
      [ShiftType.SLEEP]: '睡觉班',
      [ShiftType.MINI_NIGHT]: '小夜班',
      [ShiftType.LATE_NIGHT]: '大夜班',
      [ShiftType.VACATION]: '休假',
      [ShiftType.CUSTOM]: '自定义',
      [ShiftType.NONE]: '空班',
    };
    return names[shiftType] || shiftType;
  }, []);

  // Sync schedules robustly when employees list changes (only in local mode)
  useEffect(() => {
    if (isBackendAvailable) return; // 后端模式下不需要本地同步

    setSchedules(prev => {
      if (prev.length === 0) return prev;
      return prev.map(day => {
        const updatedRecords = employees.map(emp => {
          const existing = day.records.find(r => r.employeeId === emp.id);
          return existing || {
            employeeId: emp.id,
            date: day.date,
            type: ShiftType.NONE
          };
        });
        return { ...day, records: updatedRecords };
      });
    });
  }, [employees, isBackendAvailable]);

  // 添加员工
  const handleAddEmployee = useCallback(async () => {
    if (isBackendAvailable) {
      try {
        const newEmp = await apiCreateEmployee({
          name: '新成员',
          group_id: activeGroup,
          is_night_leader: false,
        });
        setEmployees(prev => [...prev, convertEmployeeFromDTO(newEmp)]);
      } catch (err) {
        console.error('Failed to create employee:', err);
        setError('创建员工失败');
      }
    } else {
      const newId = Date.now().toString();
      const newEmp: Employee = {
        id: newId,
        name: `新成员`,
        role: employees.length < 6 ? employees[0].role : employees[employees.length - 1].role,
        group_id: activeGroup
      };
      setEmployees(prev => [...prev, newEmp]);
    }
  }, [employees, isBackendAvailable, activeGroup]);

  // 删除员工
  const handleRemoveEmployee = useCallback(async (id: string) => {
    if (isBackendAvailable) {
      try {
        await apiDeleteEmployee(parseInt(id));
        setEmployees(prev => prev.filter(e => e.id !== id));
      } catch (err) {
        console.error('Failed to delete employee:', err);
        setError('删除员工失败');
      }
    } else {
      setEmployees(prev => prev.filter(e => e.id !== id));
    }
  }, [isBackendAvailable]);

  // 更新员工名称
  const handleUpdateEmployeeName = useCallback(async (id: string, name: string) => {
    if (isBackendAvailable) {
      try {
        await apiUpdateEmployee(parseInt(id), { name });
        setEmployees(prev => prev.map(e => e.id === id ? { ...e, name } : e));
      } catch (err) {
        console.error('Failed to update employee:', err);
        setError('更新员工失败');
      }
    } else {
      setEmployees(prev => prev.map(e => e.id === id ? { ...e, name } : e));
    }
  }, [isBackendAvailable]);

  // A/B/C 组过滤逻辑 - 使用后端返回的工作日
  const filteredSchedules = useMemo(() => {
    if (isBackendAvailable && workDays.length > 0) {
      // 后端模式：使用工作日列表过滤
      return schedules.filter(s => workDays.includes(s.date));
    } else {
      // 本地模式：使用原有逻辑
      return schedules.filter(s => {
        const day = parseInt(s.date.split('-')[2]);
        if (activeGroup === 'A') return day % 3 === 1;
        if (activeGroup === 'B') return day % 3 === 2;
        if (activeGroup === 'C') return day % 3 === 0;
        return true;
      });
    }
  }, [schedules, activeGroup, workDays, isBackendAvailable]);

  const handleSwapShifts = useCallback((source: { date: string, empId: string }, target: { date: string, empId: string }) => {
    setSchedules(prev => {
      // 先在旧状态中找到源和目标记录
      const sourceSchedule = prev.find(s => s.date === source.date);
      const targetSchedule = prev.find(s => s.date === target.date);

      if (!sourceSchedule || !targetSchedule) return prev;

      const sourceIdx = sourceSchedule.records.findIndex(r => r.employeeId === source.empId);
      const targetIdx = targetSchedule.records.findIndex(r => r.employeeId === target.empId);

      if (sourceIdx === -1 || targetIdx === -1) return prev;

      // 保存源和目标的值（从旧状态读取）
      const sourceType = sourceSchedule.records[sourceIdx].type;
      const sourceLabel = sourceSchedule.records[sourceIdx].label;
      const targetType = targetSchedule.records[targetIdx].type;
      const targetLabel = targetSchedule.records[targetIdx].label;

      // 创建新的schedules数组
      return prev.map(schedule => {
        // 如果是源日期的schedule
        if (schedule.date === source.date) {
          return {
            ...schedule,
            records: schedule.records.map((r, idx) => {
              // 修改源位置的记录
              if (idx === sourceIdx) {
                return { ...r, type: targetType, label: targetLabel };
              }
              // 如果源和目标在同一天，还要修改目标位置的记录
              if (source.date === target.date && idx === targetIdx) {
                return { ...r, type: sourceType, label: sourceLabel };
              }
              return r;
            })
          };
        }

        // 如果是目标日期的schedule（且与源日期不同）
        if (schedule.date === target.date && source.date !== target.date) {
          return {
            ...schedule,
            records: schedule.records.map((r, idx) =>
              idx === targetIdx
                ? { ...r, type: sourceType, label: sourceLabel }
                : r
            )
          };
        }

        return schedule;
      });
    });
  }, []);

  // 应用冲突调整建议
  const handleApplySuggestion = useCallback((suggestion: ConflictSuggestion) => {
    setSchedules(prev => {
      let updated = [...prev];

      suggestion.changes.forEach(change => {
        updated = updated.map(schedule => {
          if (schedule.date === change.date) {
            return {
              ...schedule,
              records: schedule.records.map(r =>
                r.employeeId === change.employeeId
                  ? { ...r, type: change.toType, label: undefined }
                  : r
              )
            };
          }
          return schedule;
        });
      });

      return updated;
    });
  }, []);

  const handleUpdateShift = useCallback((date: string, empId: string, newType: ShiftType, label?: string) => {
    // 记录用户手动修改的单元格
    setLockedCells(prev => {
      const next = new Set(prev);
      next.add(`${date}:${empId}`);
      return next;
    });

    setSchedules(prev => prev.map(s => {
      if (s.date !== date) return s;
      return {
        ...s,
        records: s.records.map(r => r.employeeId === empId ? { ...r, type: newType, label: label ?? undefined } : r)
      };
    }));

    // 实时保存到数据库
    if (isBackendAvailable) {
      updateShift({
        employee_id: parseInt(empId),
        date: date,
        shift_type: newType,
        group_id: activeGroup,
        seat_type: null,
        label: label || null,
      }).catch(err => {
        console.error('保存班次失败:', err);
        // 保存失败不影响UI，用户可以稍后手动保存整个月
      });
    }
  }, [isBackendAvailable, activeGroup]);

  const handleRescheduleRow = useCallback((date: string) => {
    setSchedules(prev => prev.map(s => {
      if (s.date !== date) return s;
      return { ...s, records: autoScheduleRowLogic(date, employees) };
    }));
  }, [employees]);

  // 智能一键排班 - 使用后端 OR-Tools 算法
  const handleAutoScheduleAll = useCallback(async () => {
    // 清空用户手动修改记录（全新排班）
    setLockedCells(new Set());
    if (isBackendAvailable) {
      setIsLoading(true);
      setError(null);

      try {
        const result = await autoGenerateSchedule({
          month: selectedMonth,
          group_id: activeGroup,
        });

        // 转换并更新排班数据
        const convertedSchedules = result.schedules.map(convertScheduleFromDTO);

        // 直接使用后端返回的排班数据替换当前排班
        setSchedules(prev => {
          const newSchedules = [...prev];
          convertedSchedules.forEach(newSchedule => {
            const idx = newSchedules.findIndex(s => s.date === newSchedule.date);
            if (idx !== -1) {
              newSchedules[idx] = newSchedule;
            } else {
              // 如果当前没有该日期的排班，直接添加
              newSchedules.push(newSchedule);
            }
          });
          // 按日期排序
          newSchedules.sort((a, b) => a.date.localeCompare(b.date));
          return newSchedules;
        });

        console.log('Auto schedule generated:', result.statistics);
      } catch (err) {
        console.error('Auto schedule failed:', err);
        setError('智能排班失败，使用本地随机排班');
        // 回退到本地随机排班
        setSchedules(prev => prev.map(s => ({
          ...s,
          records: autoScheduleRowLogic(s.date, employees)
        })));
      } finally {
        setIsLoading(false);
      }
    } else {
      // 本地模式
      setSchedules(prev => prev.map(s => ({
        ...s,
        records: autoScheduleRowLogic(s.date, employees)
      })));
    }
  }, [isBackendAvailable, selectedMonth, activeGroup, employees]);

  // 保存排班
  const handleSaveSchedule = useCallback(async () => {
    if (!isBackendAvailable) {
      alert('后端服务不可用，无法保存');
      return;
    }

    setIsSaving(true);
    setError(null);

    try {
      const result = await saveSchedule({
        month: selectedMonth,
        group_id: activeGroup,
        schedules: filteredSchedules.map(convertScheduleToDTO),
      });

      if (result.success) {
        alert(`保存成功！共保存 ${result.saved_count} 条排班记录`);
      } else {
        throw new Error(result.message);
      }
    } catch (err) {
      console.error('Save failed:', err);
      setError('保存失败');
      alert('保存失败，请重试');
    } finally {
      setIsSaving(false);
    }
  }, [isBackendAvailable, selectedMonth, activeGroup, filteredSchedules]);

  // 导出 Excel
  const handleExportSchedule = useCallback(async () => {
    if (isBackendAvailable) {
      try {
        setIsLoading(true);
        await downloadExcel(selectedMonth, activeGroup);
      } catch (err) {
        console.error('Export failed:', err);
        setError('导出失败');
        alert('导出失败，请重试');
      } finally {
        setIsLoading(false);
      }
    } else {
      alert('后端服务不可用，无法导出');
    }
  }, [isBackendAvailable, selectedMonth, activeGroup]);

  const conflicts = useMemo(() => {
    const results: Conflict[] = [];

    // 只校验当天及以后的排班
    const now = new Date();
    const todayStr = `${now.getFullYear()}-${(now.getMonth() + 1).toString().padStart(2, '0')}-${now.getDate().toString().padStart(2, '0')}`;

    const schedulesToCheck = filteredSchedules.filter(s => s.date >= todayStr);

    schedulesToCheck.forEach((schedule) => {
      // 统计各班次人数
      const shiftCounts = {
        [ShiftType.DAY]: 0,
        [ShiftType.SLEEP]: 0,
        [ShiftType.MINI_NIGHT]: 0,
        [ShiftType.LATE_NIGHT]: 0,
      };

      const activeRecords = schedule.records.filter(
        r => r.type !== ShiftType.NONE && r.type !== ShiftType.VACATION
      );

      activeRecords.forEach(r => {
        if (r.type in shiftCounts) {
          shiftCounts[r.type as keyof typeof shiftCounts]++;
        }
      });

      // A规则：检查每日岗位定员
      const requirements = {
        [ShiftType.DAY]: 6,
        [ShiftType.SLEEP]: 5,
        [ShiftType.MINI_NIGHT]: 3,
        [ShiftType.LATE_NIGHT]: 3,
      };

      Object.entries(requirements).forEach(([shiftType, required]) => {
        const actual = shiftCounts[shiftType as keyof typeof shiftCounts];
        if (actual !== required) {
          results.push({
            type: 'SLOT_COUNT_MISMATCH',
            employeeIds: [],
            date: schedule.date,
            shiftType: shiftType as ShiftType,
            message: `${schedule.date.slice(-2)}日 ${getShiftName(shiftType as ShiftType)} 需要${required}人，实际${actual}人`
          });
        }
      });

      // 检查总人数
      const totalWorking = Object.values(shiftCounts).reduce((a, b) => a + b, 0);
      if (totalWorking !== 17) {
        results.push({
          type: 'TOTAL_COUNT_MISMATCH',
          employeeIds: [],
          date: schedule.date,
          shiftType: ShiftType.NONE,
          message: `${schedule.date.slice(-2)}日 总排班人数应为17人，实际${totalWorking}人`
        });
      }

      // B规则：检查夜班主任席
      const nightTypes = [ShiftType.SLEEP, ShiftType.MINI_NIGHT, ShiftType.LATE_NIGHT];
      nightTypes.forEach(t => {
        // 前6人是主任资质
        const chiefCandidates = schedule.records.slice(0, 6).filter(r => r.type === t);
        if (chiefCandidates.length === 0) {
          results.push({
            type: 'CHIEF_MISSING',
            employeeIds: [],
            date: schedule.date,
            shiftType: t,
            message: `${schedule.date.slice(-2)}日 ${getShiftName(t)} 缺少主任席`
          });
        } else if (chiefCandidates.length > 1) {
          results.push({
            type: 'CHIEF_DUPLICATE',
            employeeIds: chiefCandidates.map(c => c.employeeId),
            date: schedule.date,
            shiftType: t,
            message: `${schedule.date.slice(-2)}日 ${getShiftName(t)} 存在多个主任席`
          });
        }
      });

      // D规则：第一列人员只能上白班和睡觉班
      if (employees.length > 0) {
        const firstEmpId = employees[0].id;
        const firstEmpRecord = schedule.records.find(r => r.employeeId === firstEmpId);
        if (firstEmpRecord && firstEmpRecord.type !== ShiftType.DAY && firstEmpRecord.type !== ShiftType.SLEEP
          && firstEmpRecord.type !== ShiftType.NONE && firstEmpRecord.type !== ShiftType.VACATION && firstEmpRecord.type !== ShiftType.CUSTOM) {
          results.push({
            type: 'ROLE_MISMATCH',
            employeeIds: [firstEmpId],
            date: schedule.date,
            shiftType: firstEmpRecord.type,
            message: `${schedule.date.slice(-2)}日 ${employees[0].name} 只能上白班或睡觉班，当前为${getShiftName(firstEmpRecord.type)}`
          });
        }
      }

      // B规则：检查避让组冲突
      avoidanceRules.forEach(rule => {
        if (!rule.memberIds || rule.memberIds.length < 2) return;

        Object.values(ShiftType).forEach(shiftType => {
          if (shiftType === ShiftType.NONE || shiftType === ShiftType.VACATION) return;

          const recordsInShift = schedule.records.filter(r => r.type === shiftType);
          const conflictingMembers = recordsInShift.filter(r =>
            rule.memberIds.includes(r.employeeId)
          );

          if (conflictingMembers.length > 1) {
            results.push({
              type: 'AVOIDANCE_CONFLICT',
              employeeIds: conflictingMembers.map(m => m.employeeId),
              date: schedule.date,
              shiftType: shiftType,
              message: `${schedule.date.slice(-2)}日 ${getShiftName(shiftType)} 存在避让组冲突`
            });
          }
        });
      });
    });

    // C规则：检查连续班次（所有班次都尽量不连续）
    // 但白班和睡觉班允许连续，不产生告警
    // 按员工构建班次序列（只看当天及以后）
    const employeeShiftSequences = new Map<string, { date: string; type: ShiftType }[]>();
    schedulesToCheck.forEach(schedule => {
      schedule.records.forEach(r => {
        if (r.type === ShiftType.NONE || r.type === ShiftType.VACATION) return;
        if (!employeeShiftSequences.has(r.employeeId)) {
          employeeShiftSequences.set(r.employeeId, []);
        }
        employeeShiftSequences.get(r.employeeId)!.push({ date: schedule.date, type: r.type });
      });
    });

    employeeShiftSequences.forEach((shifts, empId) => {
      if (shifts.length < 2) return;
      shifts.sort((a, b) => a.date.localeCompare(b.date));

      const empName = employees.find(e => e.id === empId)?.name || empId;

      // 检查连续：白班和睡觉班允许连续，其他不允许
      for (let i = 0; i < shifts.length - 1; i++) {
        if (shifts[i].type === shifts[i + 1].type) {
          // 白班和睡觉班连续是允许的，不告警
          if (shifts[i].type === ShiftType.DAY || shifts[i].type === ShiftType.SLEEP) {
            continue;
          }

          // 其他班次连续需要告警
          results.push({
            type: 'CONSECUTIVE_VIOLATION',
            employeeIds: [empId],
            date: shifts[i].date,
            shiftType: shifts[i].type,
            message: `${empName} ${shifts[i].date.slice(5)} 和 ${shifts[i + 1].date.slice(5)} 连续${getShiftName(shifts[i].type)}`
          });
        }
      }
    });

    // E规则：检查连续夜班（睡觉/小夜/大夜）不超过3个
    const nightShifts = [ShiftType.SLEEP, ShiftType.MINI_NIGHT, ShiftType.LATE_NIGHT];
    employeeShiftSequences.forEach((shifts, empId) => {
      if (shifts.length < 4) return;
      shifts.sort((a, b) => a.date.localeCompare(b.date));

      const empName = employees.find(e => e.id === empId)?.name || empId;

      // 滑动窗口检查连续4天
      for (let i = 0; i <= shifts.length - 4; i++) {
        const fourDays = shifts.slice(i, i + 4);
        const nightCount = fourDays.filter(s => nightShifts.includes(s.type)).length;

        if (nightCount > 3) {
          results.push({
            type: 'CONSECUTIVE_VIOLATION',
            employeeIds: [empId],
            date: fourDays[0].date,
            shiftType: ShiftType.SLEEP, // 用睡觉班代表夜班
            message: `${empName} ${fourDays[0].date.slice(5)}-${fourDays[3].date.slice(5)} 连续4天中有${nightCount}个夜班，不能超过3个`
          });
          break; // 每个员工只报一次
        }
      }
    });

    // F规则：检查班次间隔
    // 普通席位大夜班：最少间隔3个班，最多间隔6个班
    // 主任席大夜班：最少间隔3个班，最多间隔5个班
    // 主任席白班：最少间隔1个班，最多间隔3个班
    employeeShiftSequences.forEach((shifts, empId) => {
      if (shifts.length < 2) return;
      shifts.sort((a, b) => a.date.localeCompare(b.date));

      const empName = employees.find(e => e.id === empId)?.name || empId;
      const empIndex = employees.findIndex(e => e.id === empId);
      const isLeader = empIndex >= 0 && empIndex < 6;
      const isFirstEmp = empIndex === 0;

      // --- 大夜班间隔检查 ---
      const lateMinGap = 3;
      const lateMaxGap = isLeader ? 5 : 6;

      const lateNightIndices: number[] = [];
      for (let i = 0; i < shifts.length; i++) {
        if (shifts[i].type === ShiftType.LATE_NIGHT) {
          lateNightIndices.push(i);
        }
      }

      for (let i = 0; i < lateNightIndices.length - 1; i++) {
        const idx1 = lateNightIndices[i];
        const idx2 = lateNightIndices[i + 1];
        const gap = idx2 - idx1 - 1;

        if (gap < lateMinGap) {
          results.push({
            type: 'CONSECUTIVE_VIOLATION',
            employeeIds: [empId],
            date: shifts[idx1].date,
            shiftType: ShiftType.LATE_NIGHT,
            message: `${empName} ${shifts[idx1].date.slice(5)} 和 ${shifts[idx2].date.slice(5)} 大夜班间隔${gap}个班，需要至少${lateMinGap}个班`
          });
        } else if (gap > lateMaxGap) {
          results.push({
            type: 'CONSECUTIVE_VIOLATION',
            employeeIds: [empId],
            date: shifts[idx1].date,
            shiftType: ShiftType.LATE_NIGHT,
            message: `${empName} ${shifts[idx1].date.slice(5)} 和 ${shifts[idx2].date.slice(5)} 大夜班间隔${gap}个班，不宜超过${lateMaxGap}个班`
          });
        }
      }

      // --- 白班间隔检查（第一人除外，有固定规则） ---
      if (!isFirstEmp) {
        const dayMinGap = 1;
        const dayMaxGap = 3;

        const dayIndices: number[] = [];
        for (let i = 0; i < shifts.length; i++) {
          if (shifts[i].type === ShiftType.DAY) {
            dayIndices.push(i);
          }
        }

        for (let i = 0; i < dayIndices.length - 1; i++) {
          const idx1 = dayIndices[i];
          const idx2 = dayIndices[i + 1];
          const gap = idx2 - idx1 - 1;

          if (gap < dayMinGap) {
            results.push({
              type: 'CONSECUTIVE_VIOLATION',
              employeeIds: [empId],
              date: shifts[idx1].date,
              shiftType: ShiftType.DAY,
              message: `${empName} ${shifts[idx1].date.slice(5)} 和 ${shifts[idx2].date.slice(5)} 白班间隔${gap}个班，需要至少${dayMinGap}个班`
            });
          } else if (gap > dayMaxGap) {
            results.push({
              type: 'CONSECUTIVE_VIOLATION',
              employeeIds: [empId],
              date: shifts[idx1].date,
              shiftType: ShiftType.DAY,
              message: `${empName} ${shifts[idx1].date.slice(5)} 和 ${shifts[idx2].date.slice(5)} 白班间隔${gap}个班，不宜超过${dayMaxGap}个班`
            });
          }
        }
      }
    });

    // 为每个冲突生成调整建议
    return results.map(conflict => ({
      ...conflict,
      suggestion: generateConflictSuggestion(conflict, filteredSchedules, employees, lockedCells)
    }));
  }, [filteredSchedules, avoidanceRules, getShiftName, employees, lockedCells]);

  const stats = useMemo(() => {
    const totalWorkingShifts = schedules.reduce((acc, s) =>
      acc + s.records.filter(r => r.type !== ShiftType.VACATION && r.type !== ShiftType.SLEEP && r.type !== ShiftType.NONE).length, 0);

    return {
      period: `${year}-${(month + 1).toString().padStart(2, '0')}-01 至 月底`,
      totalHours: Math.round(totalWorkingShifts * 8 / (employees.length || 1)),
      personnelCount: employees.length,
      conflictRate: parseFloat(((conflicts.length / (Math.max(1, schedules.length * employees.length))) * 100).toFixed(1)),
      targetRate: 100
    };
  }, [schedules, conflicts, employees, year, month]);

  return (
    <div className="flex flex-col h-screen bg-slate-50 dark:bg-slate-950">
      {/* 状态提示 */}
      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-2 text-sm">
          {error}
          <button
            className="ml-4 text-red-500 hover:text-red-700"
            onClick={() => setError(null)}
          >
            关闭
          </button>
        </div>
      )}

      {!isBackendAvailable && (
        <div className="bg-yellow-100 border border-yellow-400 text-yellow-700 px-4 py-2 text-sm">
          后端服务不可用，当前为本地模式（数据不会保存到服务器）
        </div>
      )}

      <MatrixHeader
        activeGroup={activeGroup}
        onGroupChange={setActiveGroup}
        selectedMonth={selectedMonth}
        onMonthChange={setSelectedMonth}
        onAutoSchedule={handleAutoScheduleAll}
        onSaveSchedule={handleSaveSchedule}
        onExportSchedule={handleExportSchedule}
        isLoading={isLoading}
        isSaving={isSaving}
        isBackendAvailable={isBackendAvailable}
      />

      <main className="flex-1 overflow-auto custom-scrollbar p-4">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-lg text-gray-500">加载中...</div>
          </div>
        ) : (
          <MatrixGrid
            employees={employees}
            onAddEmployee={handleAddEmployee}
            onRemoveEmployee={handleRemoveEmployee}
            onUpdateEmployeeName={handleUpdateEmployeeName}
            schedules={filteredSchedules}
            conflicts={conflicts}
            onUpdateShift={handleUpdateShift}
            onSwapShifts={handleSwapShifts}
            onRescheduleRow={handleRescheduleRow}
            onApplySuggestion={handleApplySuggestion}
            showWorkDaySelector={showWorkDaySelector}
            selectedMonth={selectedMonth}
            onSetFirstWorkDay={handleSetFirstWorkDay}
          />
        )}
      </main>

      <MatrixFooter stats={stats} conflicts={conflicts} />
    </div>
  );
};

export default App;
