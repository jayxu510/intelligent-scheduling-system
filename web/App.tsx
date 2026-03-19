
import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { generateMonthSchedules, autoScheduleRowLogic } from './data';
import { ShiftType, DailySchedule, Conflict, Employee, ShiftRecord, EmployeeRole, AvoidanceRule, ConflictSuggestion } from './types';
import { generateConflictSuggestion } from './conflictResolver';
import MatrixHeader from './components/MatrixHeader';
import MatrixGrid from './components/MatrixGrid';
import MatrixFooter from './components/MatrixFooter';
import {
  fetchInitData,
  autoGenerateSchedule,
  validateMonthSchedule,
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
  const [lockedCells, setLockedCells] = useState<Set<string>>(new Set()); // 锁定的单元格
  const [backupSchedules, setBackupSchedules] = useState<DailySchedule[] | null>(null); // 一键优化前的备份
  const [previousSchedules, setPreviousSchedules] = useState<DailySchedule[]>([]);
  const [previousWorkDays, setPreviousWorkDays] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isBackendAvailable, setIsBackendAvailable] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [showWorkDaySelector, setShowWorkDaySelector] = useState(false);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const matrixScrollRef = useRef<HTMLDivElement>(null);
  const shouldStickToBottomRef = useRef(true);

  const [year, month] = useMemo(() => {
    const parts = selectedMonth.split('-');
    return [parseInt(parts[0]), parseInt(parts[1]) - 1];
  }, [selectedMonth]);

  const previousMonth = useMemo(() => {
    const [yearStr, monthStr] = selectedMonth.split('-');
    const currentYear = parseInt(yearStr);
    const currentMonth = parseInt(monthStr);
    const prevDate = new Date(currentYear, currentMonth - 2, 1);
    const prevYear = prevDate.getFullYear();
    const prevMonth = (prevDate.getMonth() + 1).toString().padStart(2, '0');
    return `${prevYear}-${prevMonth}`;
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
      setPreviousSchedules([]);
      setPreviousWorkDays([]);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const [currentData, previousData] = await Promise.all([
        fetchInitData(selectedMonth, activeGroup),
        fetchInitData(previousMonth, activeGroup)
      ]);

      // 转换员工数据
      const convertedEmployees = currentData.employees.map(convertEmployeeFromDTO);
      setEmployees(convertedEmployees);

      // 转换排班数据
      const convertedSchedules = currentData.schedules.map(convertScheduleFromDTO);
      setSchedules(convertedSchedules);

      // 设置工作日
      setWorkDays(currentData.work_days);

      // 判断是否需要显示工作日选择器
      // 当工作日列表为空时，显示选择器
      setShowWorkDaySelector(currentData.work_days.length === 0);

      // 设置避让规则
      setAvoidanceRules(currentData.avoidance_rules.map(r => ({
        id: r.id.toString(),
        name: r.name || undefined,
        memberIds: r.member_ids.map(id => id.toString()),
        description: r.description || undefined,
      })));

      // 上个月排班
      const previousSchedulesConverted = previousData.schedules.map(convertScheduleFromDTO);
      setPreviousSchedules(previousSchedulesConverted);
      setPreviousWorkDays(previousData.work_days || []);

      console.log('Data loaded from backend:', {
        employees: convertedEmployees.length,
        schedules: convertedSchedules.length,
        workDays: currentData.work_days.length,
      });
    } catch (err) {
      console.error('Failed to load init data:', err);
      setError('加载数据失败，请检查后端服务');
      // 清空数据，但显示工作日选择器
      setEmployees([]);
      setSchedules([]);
      setWorkDays([]);
      setPreviousSchedules([]);
      setPreviousWorkDays([]);
      setShowWorkDaySelector(true); // 👈 关键修改：失败时也显示选择器
    } finally {
      setIsLoading(false);
    }
  }, [isBackendAvailable, selectedMonth, previousMonth, activeGroup, year, month]);

null

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

  const scrollToBottom = useCallback(() => {
    const container = matrixScrollRef.current;
    if (!container) return;
    container.scrollTop = container.scrollHeight;
  }, []);

  const handleScroll = useCallback(() => {
    const container = matrixScrollRef.current;
    if (!container) return;
    const tolerance = 6;
    shouldStickToBottomRef.current = container.scrollTop + container.clientHeight >= container.scrollHeight - tolerance;
  }, []);

  useEffect(() => {
    loadInitData();
    setLockedCells(new Set());
    setBackupSchedules(null);
    shouldStickToBottomRef.current = true;
  }, [selectedMonth, activeGroup, isBackendAvailable, loadInitData]);



  // ==========================================
  // 新增：统一调用后端校验的函数
  // ==========================================
  const runValidation = useCallback(async (currentSchedules: DailySchedule[]) => {
    // 如果后端没连上，或者没有排班数据，就不校验
    if (!isBackendAvailable || !currentSchedules || currentSchedules.length === 0) {
      setConflicts([]);
      return;
    }

    try {
      // 1. 把前端的排班数据转成后端 API 需要的格式
      const dtos = currentSchedules.map(convertScheduleToDTO);

      // 2. 发送给后端校验
      const res = await validateMonthSchedule(dtos);

      // 3. 把后端返回的错误，转换成前端展示需要的 Conflict 格式
      const formattedConflicts: Conflict[] = res.errors.map((err: any) => {
        // 尝试从后端的报错文字中提取出班次类型，这样就能继续完美支持“调整建议”功能
        let inferredShiftType = ShiftType.NONE;
        if (err.message.includes('白班')) inferredShiftType = ShiftType.DAY;
        else if (err.message.includes('睡觉班')) inferredShiftType = ShiftType.SLEEP;
        else if (err.message.includes('小夜班')) inferredShiftType = ShiftType.MINI_NIGHT;
        else if (err.message.includes('大夜班')) inferredShiftType = ShiftType.LATE_NIGHT;

        const conflict: Conflict = {
          type: err.type as any,
          date: err.date,
          message: err.message,
          shiftType: inferredShiftType !== ShiftType.NONE ? inferredShiftType : undefined,
          employeeIds: (err.employee_ids || []).map(String), // 后端发来的是数字，前端需要转成字符串
        };

        // 重新生成针对这个冲突的“智能调整建议”
        const suggestion = generateConflictSuggestion(
          conflict,
          currentSchedules,
          employees,
          lockedCells
        );
        if (suggestion) {
            conflict.suggestion = suggestion;
        }

        return conflict;
      });

      // 4. 更新状态，页面上就会自动出现红框和右下角的报错列表
      setConflicts(formattedConflicts);
    } catch (error) {
      console.error('调用后端校验接口失败:', error);
    }
  }, [isBackendAvailable, employees, lockedCells]);

  // ==========================================
  // 新增：监听排班表变化，自动触发后端校验
  // ==========================================
  useEffect(() => {
    // 只要 schedules 发生任何变化（无论是拉取数据、一键排班还是手动修改）
    // 都会自动把最新的表发给后端检查
    runValidation(schedules);
  }, [schedules, runValidation]);

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
    // 同步员工和排班数据：确保每个员工在每个日期都有记录
    setSchedules(prev => {
      if (prev.length === 0 || employees.length === 0) return prev;
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
  }, [employees]);

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

  const previousMonthSchedules = useMemo(() => {
    if (isBackendAvailable && previousWorkDays.length > 0) {
      return previousSchedules.filter(s => previousWorkDays.includes(s.date));
    }
    return previousSchedules.filter(s => s.date.startsWith(previousMonth));
  }, [previousSchedules, previousWorkDays, previousMonth, isBackendAvailable]);

  const combinedSchedules = useMemo(() => {
    const merged = [...previousMonthSchedules, ...filteredSchedules];
    return merged.sort((a, b) => a.date.localeCompare(b.date));
  }, [previousMonthSchedules, filteredSchedules]);

  useEffect(() => {
    if (shouldStickToBottomRef.current) {
      requestAnimationFrame(scrollToBottom);
    }
  }, [combinedSchedules, scrollToBottom]);
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
    // 更新前端状态
    setSchedules(prev => {
      // 创建新的数组，确保引用改变
      const updated = prev.map(s => {
        if (s.date !== date) return s;

        // 创建新的 records 数组
        const updatedRecords = s.records.map(r => {
          if (r.employeeId === empId) {
            // 创建新的 record 对象
            return {
              ...r,
              type: newType,
              label: label ?? undefined,
              // 确保所有字段都被复制
              employeeId: r.employeeId,
              date: r.date,
              seatType: r.seatType,
              isLocked: r.isLocked
            };
          }
          return r;
        });

        // 创建新的 schedule 对象
        return {
          date: s.date,
          dayOfWeek: s.dayOfWeek,
          records: updatedRecords
        };
      });

      return updated;
    });

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

  const findScheduleSource = useCallback((date: string): DailySchedule[] => {
    if (date.startsWith(previousMonth)) {
      return previousMonthSchedules;
    }
    return filteredSchedules;
  }, [previousMonth, previousMonthSchedules, filteredSchedules]);

  const handleUpdateShiftUnified = useCallback((date: string, empId: string, newType: ShiftType, label?: string) => {
    if (date.startsWith(previousMonth)) {
      return;
    }
    handleUpdateShift(date, empId, newType, label);
  }, [handleUpdateShift, previousMonth]);

  const handleSwapShiftsUnified = useCallback((source: { date: string, empId: string }, target: { date: string, empId: string }) => {
    if (source.date.startsWith(previousMonth) || target.date.startsWith(previousMonth)) {
      return;
    }
    handleSwapShifts(source, target);
  }, [handleSwapShifts, previousMonth]);

  const handleRescheduleRowUnified = useCallback((date: string) => {
    if (date.startsWith(previousMonth)) {
      return;
    }
    handleRescheduleRow(date);
  }, [handleRescheduleRow, previousMonth]);

  const handleApplySuggestionUnified = useCallback((suggestion: ConflictSuggestion) => {
    handleApplySuggestion(suggestion);
  }, [handleApplySuggestion]);

  // 切换单元格锁定状态
  const toggleCellLock = useCallback((date: string, empId: string) => {
    const cellKey = `${date}-${empId}`;
    setLockedCells(prev => {
      const newSet = new Set(prev);
      if (newSet.has(cellKey)) {
        newSet.delete(cellKey);
      } else {
        newSet.add(cellKey);
      }
      return newSet;
    });

    // 更新 ShiftRecord 的 isLocked 属性
    setSchedules(prev => prev.map(s => {
      if (s.date !== date) return s;
      return {
        ...s,
        records: s.records.map(r => {
          if (r.employeeId === empId) {
            const cellKey = `${date}-${empId}`;
            const isLocked = !lockedCells.has(cellKey);
            return { ...r, isLocked };
          }
          return r;
        })
      };
    }));
  }, [lockedCells]);

  // 锁定整行
  const lockRow = useCallback((date: string) => {
    setLockedCells(prev => {
      const newSet = new Set(prev);
      employees.forEach(emp => {
        newSet.add(`${date}-${emp.id}`);
      });
      return newSet;
    });

    // 更新 ShiftRecord 的 isLocked 属性
    setSchedules(prev => prev.map(s => {
      if (s.date !== date) return s;
      return {
        ...s,
        records: s.records.map(r => ({ ...r, isLocked: true }))
      };
    }));
  }, [employees]);

  // 解锁整行
  const unlockRow = useCallback((date: string) => {
    setLockedCells(prev => {
      const newSet = new Set(prev);
      employees.forEach(emp => {
        newSet.delete(`${date}-${emp.id}`);
      });
      return newSet;
    });

    // 更新 ShiftRecord 的 isLocked 属性
    setSchedules(prev => prev.map(s => {
      if (s.date !== date) return s;
      return {
        ...s,
        records: s.records.map(r => ({ ...r, isLocked: false }))
      };
    }));
  }, [employees]);

  // 锁定整列
  const lockColumn = useCallback((empId: string) => {
    setLockedCells(prev => {
      const newSet = new Set(prev);
      schedules.forEach(schedule => {
        newSet.add(`${schedule.date}-${empId}`);
      });
      return newSet;
    });

    // 更新 ShiftRecord 的 isLocked 属性
    setSchedules(prev => prev.map(s => ({
      ...s,
      records: s.records.map(r =>
        r.employeeId === empId ? { ...r, isLocked: true } : r
      )
    })));
  }, [schedules]);

  // 解锁整列
  const unlockColumn = useCallback((empId: string) => {
    setLockedCells(prev => {
      const newSet = new Set(prev);
      schedules.forEach(schedule => {
        newSet.delete(`${schedule.date}-${empId}`);
      });
      return newSet;
    });

    // 更新 ShiftRecord 的 isLocked 属性
    setSchedules(prev => prev.map(s => ({
      ...s,
      records: s.records.map(r =>
        r.employeeId === empId ? { ...r, isLocked: false } : r
      )
    })));
  }, [schedules]);

  // 一键优化（保留锁定的单元格，只优化当日及以后）
  const handleOptimizeSchedule = useCallback(async () => {
    if (!isBackendAvailable) {
      alert('后端服务不可用，无法优化');
      return;
    }

    // 获取今天的日期
    const today = new Date().toISOString().split('T')[0];

    // 过滤出今天及以后的排班
    const futureSchedules = schedules.filter(s => s.date >= today);

    if (futureSchedules.length === 0) {
      alert('没有需要优化的日期（当日及以后）');
      return;
    }

    // 备份当前排班
    setBackupSchedules(schedules);
    setIsLoading(true);
    setError(null);

    try {
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

      // 转换并更新排班数据
      const convertedSchedules = result.schedules.map(convertScheduleFromDTO);

      setSchedules(prev => {
        const newSchedules = [...prev];
        convertedSchedules.forEach(newSchedule => {
          const idx = newSchedules.findIndex(s => s.date === newSchedule.date);
          if (idx !== -1) {
            // 保留锁定单元格的数据
            const mergedRecords = newSchedule.records.map(newRecord => {
              const cellKey = `${newSchedule.date}-${newRecord.employeeId}`;
              if (lockedCells.has(cellKey)) {
                // 使用原有的锁定数据
                const oldRecord = prev[idx].records.find(r => r.employeeId === newRecord.employeeId);
                return oldRecord ? { ...oldRecord, isLocked: true } : newRecord;
              }
              return newRecord;
            });
            newSchedules[idx] = { ...newSchedule, records: mergedRecords };
          } else {
            newSchedules.push(newSchedule);
          }
        });
        newSchedules.sort((a, b) => a.date.localeCompare(b.date));
        return newSchedules;
      });

      console.log('Schedule optimized:', result.statistics);
      alert(`优化成功！已优化 ${convertedSchedules.length} 天的排班`);
    } catch (err) {
      console.error('Optimize schedule failed:', err);
      setError('优化排班失败');
      alert('优化失败，请重试');
    } finally {
      setIsLoading(false);
    }
  }, [isBackendAvailable, selectedMonth, activeGroup, schedules, lockedCells]);

  // 回退到优化前的状态
  const handleUndoOptimize = useCallback(() => {
    if (backupSchedules) {
      setSchedules(backupSchedules);
      setBackupSchedules(null);
    }
  }, [backupSchedules]);

  // 智能一键排班 - 使用后端 OR-Tools 算法
  const handleAutoScheduleAll = useCallback(async () => {
    // 不清空锁定记录，保留用户锁定的单元格
    if (isBackendAvailable) {
      setIsLoading(true);
      setError(null);

      try {
        // 收集锁定的单元格数据
        const lockedRecords = schedules.flatMap(schedule =>
          schedule.records.filter(r => {
            const cellKey = `${schedule.date}-${r.employeeId}`;
            return lockedCells.has(cellKey);
          })
        );

        const result = await autoGenerateSchedule({
          month: selectedMonth,
          group_id: activeGroup,
          locked_records: lockedRecords.map(r => ({
            employee_id: parseInt(r.employeeId),
            date: r.date,
            shift_type: r.type,
          })),
        });

        // 转换并更新排班数据
        const convertedSchedules = result.schedules.map(convertScheduleFromDTO);

        // 直接使用后端返回的排班数据替换当前排班
        setSchedules(prev => {
          const newSchedules = [...prev];
          convertedSchedules.forEach(newSchedule => {
            const idx = newSchedules.findIndex(s => s.date === newSchedule.date);
            if (idx !== -1) {
              // 保留锁定单元格的数据
              const mergedRecords = newSchedule.records.map(newRecord => {
                const cellKey = `${newSchedule.date}-${newRecord.employeeId}`;
                if (lockedCells.has(cellKey)) {
                  // 使用原有的锁定数据
                  const oldRecord = prev[idx].records.find(r => r.employeeId === newRecord.employeeId);
                  return oldRecord ? { ...oldRecord, isLocked: true } : newRecord;
                }
                return newRecord;
              });
              newSchedules[idx] = { ...newSchedule, records: mergedRecords };
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
  }, [isBackendAvailable, selectedMonth, activeGroup, employees, schedules, lockedCells]);

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

      <main className="flex-1 overflow-hidden p-2">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-lg text-gray-500">加载中...</div>
          </div>
        ) : (
          <div className="w-full h-full overflow-auto">
            <div ref={matrixScrollRef} className="w-full h-full custom-scrollbar" onScroll={handleScroll}>
              <MatrixGrid
                employees={employees}
                onAddEmployee={handleAddEmployee}
                onRemoveEmployee={handleRemoveEmployee}
                onUpdateEmployeeName={handleUpdateEmployeeName}
                schedules={combinedSchedules}
                conflicts={conflicts}
                onUpdateShift={handleUpdateShiftUnified}
                onSwapShifts={handleSwapShiftsUnified}
                onRescheduleRow={handleRescheduleRowUnified}
                onApplySuggestion={handleApplySuggestionUnified}
                showWorkDaySelector={showWorkDaySelector}
                selectedMonth={selectedMonth}
                onSetFirstWorkDay={handleSetFirstWorkDay}
                lockedCells={lockedCells}
                onToggleCellLock={toggleCellLock}
                onLockRow={lockRow}
                onUnlockRow={unlockRow}
                onLockColumn={lockColumn}
                onUnlockColumn={unlockColumn}
                compact
                headerInsertIndex={previousMonthSchedules.length}
              />
            </div>
          </div>
        )}
      </main>

      <MatrixFooter
        stats={stats}
        conflicts={conflicts}
        employees={employees}
        onOptimize={handleOptimizeSchedule}
        onUndoOptimize={handleUndoOptimize}
        canUndo={backupSchedules !== null}
      />
    </div>
  );
};

export default App;
