
import React, { useState, useRef, useEffect } from 'react';
import { Employee, DailySchedule, ShiftType, ShiftRecord, Conflict, EmployeeRole, ConflictSuggestion } from '../types';

interface MatrixGridProps {
  employees: Employee[];
  onAddEmployee: () => void;
  onRemoveEmployee: (id: string) => void;
  onUpdateEmployeeName: (id: string, name: string) => void;
  schedules: DailySchedule[];
  conflicts: Conflict[];
  onUpdateShift: (date: string, empId: string, newType: ShiftType, label?: string) => void;
  onSwapShifts: (source: { date: string, empId: string }, target: { date: string, empId: string }) => void;
  onRescheduleRow: (date: string) => void;
  onApplySuggestion: (suggestion: ConflictSuggestion) => void;
  showWorkDaySelector?: boolean;
  selectedMonth?: string;
  onSetFirstWorkDay?: (day: number) => void;
  lockedCells?: Set<string>;
  onToggleCellLock?: (date: string, empId: string) => void;
  onLockRow?: (date: string) => void;
  onUnlockRow?: (date: string) => void;
  onLockColumn?: (empId: string) => void;
  onUnlockColumn?: (empId: string) => void;
}

// 内部组件：处理中文输入法的输入框
const EmployeeNameInput: React.FC<{
  value: string;
  onUpdate: (val: string) => void;
}> = ({ value, onUpdate }) => {
  const [localValue, setLocalValue] = useState(value);

  // 当外部 value 变化时（例如重新加载数据），同步到本地状态
  React.useEffect(() => {
    setLocalValue(value);
  }, [value]);

  const handleBlur = () => {
    if (localValue !== value) {
      onUpdate(localValue);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.currentTarget.blur(); // 触发 blur 保存
    }
  };

  return (
    <input
      value={localValue}
      onChange={(e) => setLocalValue(e.target.value)}
      onBlur={handleBlur}
      onKeyDown={handleKeyDown}
      className="w-full text-center text-[12px] font-black bg-transparent border-none focus:ring-1 focus:ring-primary rounded p-0 text-slate-700 dark:text-slate-200 outline-none"
    />
  );
};

const MatrixGrid: React.FC<MatrixGridProps> = ({
  employees, onAddEmployee, onRemoveEmployee, onUpdateEmployeeName, schedules, conflicts,
  onUpdateShift, onSwapShifts, onRescheduleRow, onApplySuggestion,
  showWorkDaySelector = false,
  selectedMonth = '',
  onSetFirstWorkDay,
  lockedCells = new Set(),
  onToggleCellLock,
  onLockRow,
  onUnlockRow,
  onLockColumn,
  onUnlockColumn
}) => {
  const [dragInfo, setDragInfo] = useState<{ date: string, empId: string } | null>(null);
  const [selectedDay, setSelectedDay] = useState<number>(0);

  // 计算当月天数
  const daysInMonth = React.useMemo(() => {
    if (!selectedMonth) return 31;
    const [year, month] = selectedMonth.split('-').map(Number);
    return new Date(year, month, 0).getDate();
  }, [selectedMonth]);

  const handleDaySelect = (day: number) => {
    setSelectedDay(day);
    if (onSetFirstWorkDay) {
      onSetFirstWorkDay(day);
    }
  };

  const getShiftConflict = (date: string, type: ShiftType) => {
    return conflicts.find(c => c.date === date && c.shiftType === type);
  };

  const checkIndividualConflict = (date: string, empId: string) => {
    return conflicts.some(c => c.date === date && c.employeeIds.includes(empId));
  };

  return (
    <div className="inline-block min-w-full bg-white dark:bg-slate-900 shadow-2xl rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden">
      {/* 工作日选择器 */}
      {showWorkDaySelector && (
        <div className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-slate-800 dark:to-slate-700 border-b-2 border-blue-200 dark:border-blue-900 p-6">
          <div className="max-w-2xl mx-auto">
            <div className="flex items-center gap-3 mb-4">
              <span className="material-icons text-blue-600 dark:text-blue-400 text-3xl">calendar_month</span>
              <div>
                <h3 className="text-lg font-black text-slate-800 dark:text-slate-100">设置本月工作日</h3>
                <p className="text-sm text-slate-600 dark:text-slate-400">请选择本月第一个工作日，系统将自动生成所有工作日（间隔2天）</p>
              </div>
            </div>

            <div className="flex items-center gap-4">
              <label className="text-sm font-bold text-slate-700 dark:text-slate-300 whitespace-nowrap">
                首个工作日：
              </label>
              <select
                value={selectedDay}
                onChange={(e) => handleDaySelect(parseInt(e.target.value))}
                className="flex-1 px-4 py-3 bg-white dark:bg-slate-800 border-2 border-blue-300 dark:border-blue-700 rounded-lg text-sm font-bold text-slate-800 dark:text-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all"
              >
                <option value={0}>请选择日期...</option>
                {Array.from({ length: daysInMonth }, (_, i) => i + 1).map(day => (
                  <option key={day} value={day}>
                    {selectedMonth.split('-')[0]}年{selectedMonth.split('-')[1]}月{day}日
                  </option>
                ))}
              </select>

              {selectedDay > 0 && (
                <div className="flex items-center gap-2 px-4 py-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                  <span className="material-icons text-blue-600 dark:text-blue-400 text-sm">info</span>
                  <span className="text-xs font-bold text-blue-700 dark:text-blue-300">
                    将生成：{selectedDay}日、{selectedDay + 3}日、{selectedDay + 6}日...
                  </span>
                </div>
              )}
            </div>

            <div className="mt-4 p-3 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg">
              <div className="flex items-start gap-2">
                <span className="material-icons text-yellow-600 dark:text-yellow-400 text-sm mt-0.5">lightbulb</span>
                <p className="text-xs text-yellow-800 dark:text-yellow-200">
                  <strong>提示：</strong>设置后将自动按照"工作1天，休息2天"的规律生成整月工作日。例如选择1日，将生成1、4、7、10...等工作日。
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      <div
        className="grid"
        style={{
          gridTemplateColumns: `80px repeat(${employees.length}, 70px) 40px 140px 80px`
        }}
      >
        {/* Sticky Header */}
        <div className="sticky top-0 z-50 h-16 bg-slate-100 dark:bg-slate-800 border-b border-r border-slate-200 dark:border-slate-700 flex items-center justify-center text-[11px] font-bold text-slate-400">日期</div>
        {employees.map((emp, idx) => {
          // 检查该列是否全部锁定
          const isColumnLocked = schedules.length > 0 && schedules.every(s => lockedCells.has(`${s.date}-${emp.id}`));

          return (
            <div key={emp.id} className="sticky top-0 z-50 h-16 bg-white dark:bg-slate-800 border-b border-r border-slate-200 dark:border-slate-700 p-1 group">
              <div className="flex flex-col items-center h-full justify-between">
                <EmployeeNameInput
                  value={emp.name}
                  onUpdate={(val) => onUpdateEmployeeName(emp.id, val)}
                />
                <span className={`text-[8px] uppercase font-bold tracking-widest ${idx < 6 ? 'text-primary' : 'text-slate-400'}`}>
                  {idx < 6 ? '主任' : '普通'}
                </span>
                <button
                  onClick={() => onRemoveEmployee(emp.id)}
                  className="absolute top-0 right-0 p-0.5 opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-600 transition-all"
                >
                  <span className="material-icons text-[12px]">cancel</span>
                </button>
                {/* 锁定/解锁整列按钮 */}
                <button
                  onClick={() => isColumnLocked ? onUnlockColumn?.(emp.id) : onLockColumn?.(emp.id)}
                  className="absolute bottom-0 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-all"
                  title={isColumnLocked ? "解锁整列" : "锁定整列"}
                >
                  <span className={`material-icons text-[12px] ${isColumnLocked ? 'text-green-600' : 'text-slate-400 hover:text-green-600'}`}>
                    {isColumnLocked ? 'lock' : 'lock_open'}
                  </span>
                </button>
              </div>
            </div>
          );
        })}
        <div className="sticky top-0 z-50 h-16 bg-slate-100 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 flex items-center justify-center gap-2 px-2">
          <button onClick={onAddEmployee} className="w-6 h-6 rounded-full bg-primary/10 text-primary hover:bg-primary hover:text-white transition-all shadow-sm flex items-center justify-center shrink-0" title="添加员工">
            <span className="material-icons text-[16px]">add</span>
          </button>
          {employees.length === 0 && (
            <div className="inline-flex items-center gap-1 px-2 py-1 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded text-[10px] text-yellow-800 dark:text-yellow-200 whitespace-nowrap">
              <span className="material-icons text-[12px]">warning</span>
              <span className="font-bold">请添加人员</span>
            </div>
          )}
        </div>
        <div className="sticky top-0 right-0 z-50 h-16 bg-slate-100 dark:bg-slate-800 border-b border-l border-slate-200 dark:border-slate-700 flex items-center justify-center text-[11px] font-black text-primary uppercase tracking-widest">统计</div>
        <div className="sticky top-0 right-0 z-50 h-16 bg-slate-100 dark:bg-slate-800 border-b border-l border-slate-200 dark:border-slate-700 flex items-center justify-center text-[11px] font-black text-slate-400 uppercase tracking-widest">锁定</div>

        {/* Schedule Rows */}
        {schedules.map((schedule) => {
          const counts = {
            day: schedule.records.filter(r => r.type === ShiftType.DAY).length,
            sleep: schedule.records.filter(r => r.type === ShiftType.SLEEP).length,
            mini: schedule.records.filter(r => r.type === ShiftType.MINI_NIGHT).length,
            late: schedule.records.filter(r => r.type === ShiftType.LATE_NIGHT).length,
            total: schedule.records.filter(r => r.type !== ShiftType.NONE && r.type !== ShiftType.VACATION).length
          };

          return (
            <React.Fragment key={schedule.date}>
              <div className="sticky left-0 z-30 h-14 bg-white dark:bg-slate-900 border-b border-r border-slate-200 dark:border-slate-800 flex flex-col items-center justify-center">
                <span className="text-[10px] text-slate-400 font-medium">{schedule.date.slice(5)}</span>
                <span className="text-[12px] font-black">{schedule.dayOfWeek}</span>
              </div>
              
              {employees.map((emp, idx) => {
                let record = schedule.records.find(r => r.employeeId === emp.id);

                // 如果找不到记录（例如新添加的员工），创建一个默认的空记录
                if (!record) {
                  record = {
                    employeeId: emp.id,
                    date: schedule.date,
                    type: ShiftType.NONE
                  };
                }

                const chiefConflict = getShiftConflict(schedule.date, record.type);
                const isIndivConflict = checkIndividualConflict(schedule.date, emp.id);

                // 找到与该单元格相关的所有冲突
                const cellConflicts = conflicts.filter(c =>
                  c.date === schedule.date && (
                    c.employeeIds.includes(emp.id) ||
                    c.shiftType === record.type ||
                    c.type === 'SLOT_COUNT_MISMATCH' ||
                    c.type === 'TOTAL_COUNT_MISMATCH'
                  )
                );

                return (
                  <ShiftCell
                    key={emp.id}
                    record={record}
                    employeeName={emp.name}
                    isChiefCandidate={idx < 6}
                    isChiefMissing={!!chiefConflict}
                    isIndivConflict={isIndivConflict}
                    cellConflicts={cellConflicts}
                    isLocked={lockedCells.has(`${schedule.date}-${emp.id}`)}
                    onToggleLock={() => onToggleCellLock?.(schedule.date, emp.id)}
                    onUpdate={(type: ShiftType, label?: string) => {
                      onUpdateShift(schedule.date, emp.id, type, label);
                    }}
                    onApplySuggestion={onApplySuggestion}
                    onDragStart={() => setDragInfo({ date: schedule.date, empId: emp.id })}
                    onDrop={() => {
                      if (dragInfo) onSwapShifts(dragInfo, { date: schedule.date, empId: emp.id });
                      setDragInfo(null);
                    }}
                  />
                );
              })}

              <div className="h-14 border-b border-slate-200 dark:border-slate-800 flex items-center justify-center">
                <button 
                  onClick={() => onRescheduleRow(schedule.date)}
                  className="p-1 rounded bg-slate-50 dark:bg-slate-800 text-slate-400 hover:bg-primary hover:text-white transition-all shadow-sm border border-slate-200 dark:border-slate-700"
                  title="重新生成该日排班"
                >
                  <span className="material-icons text-[14px]">refresh</span>
                </button>
              </div>

              {/* Pixel Perfect Statistics Column */}
              <div className="sticky right-0 h-14 bg-slate-50 dark:bg-slate-800 border-l border-b border-slate-200 dark:border-slate-700 flex items-center px-2 z-30">
                <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 flex-1 items-center">
                  <div className="flex justify-between items-center text-[10px] font-black">
                    <span className="text-amber-500 mr-1">白</span>
                    <span className="text-slate-600 dark:text-slate-300">{counts.day}</span>
                  </div>
                  <div className="flex justify-between items-center text-[10px] font-black">
                    <span className="text-slate-500 mr-1">睡</span>
                    <span className="text-slate-600 dark:text-slate-300">{counts.sleep}</span>
                  </div>
                  <div className="flex justify-between items-center text-[10px] font-black">
                    <span className="text-blue-500 mr-1">小</span>
                    <span className="text-slate-600 dark:text-slate-300">{counts.mini}</span>
                  </div>
                  <div className="flex justify-between items-center text-[10px] font-black">
                    <span className="text-indigo-800 dark:text-indigo-400 mr-1">大</span>
                    <span className="text-slate-600 dark:text-slate-300">{counts.late}</span>
                  </div>
                </div>
                <div className="w-[1px] h-8 bg-slate-300 dark:bg-slate-600 mx-1"></div>
                <div className="flex flex-col items-center justify-center min-w-[32px] ml-1">
                   <span className="text-[11px] text-primary font-black leading-none">{counts.total}</span>
                   <span className="text-[9px] text-slate-400 mt-0.5 tracking-tighter">/{employees.length}</span>
                </div>
              </div>

              {/* 锁定整行按钮 */}
              <div className="h-14 border-b border-l border-slate-200 dark:border-slate-800 flex items-center justify-center group">
                {(() => {
                  const isRowLocked = employees.length > 0 && employees.every(emp => lockedCells.has(`${schedule.date}-${emp.id}`));
                  return (
                    <button
                      onClick={() => isRowLocked ? onUnlockRow?.(schedule.date) : onLockRow?.(schedule.date)}
                      className="p-1 rounded bg-slate-50 dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 transition-all shadow-sm border border-slate-200 dark:border-slate-700"
                      title={isRowLocked ? "解锁整行" : "锁定整行"}
                    >
                      <span className={`material-icons text-[14px] ${isRowLocked ? 'text-green-600' : 'text-slate-400'}`}>
                        {isRowLocked ? 'lock' : 'lock_open'}
                      </span>
                    </button>
                  );
                })()}
              </div>
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};

const SHIFT_OPTIONS = [
  { type: ShiftType.DAY, label: '白班', color: 'bg-[#facc15] text-slate-900' },
  { type: ShiftType.MINI_NIGHT, label: '小夜', color: 'bg-[#3b82f6] text-white' },
  { type: ShiftType.LATE_NIGHT, label: '大夜', color: 'bg-[#1e3a8a] text-white' },
  { type: ShiftType.SLEEP, label: '睡觉', color: 'bg-[#9ca3af] text-white' },
  { type: ShiftType.VACATION, label: '休假', color: 'bg-[#4ade80] text-slate-900' },
  { type: ShiftType.CUSTOM, label: '自定义', color: 'bg-[#f97316] text-white' },
  { type: ShiftType.NONE, label: '空白', color: 'bg-white border border-slate-300 text-slate-400' },
];

const ShiftCell: React.FC<{
  record: ShiftRecord,
  employeeName: string,
  isChiefCandidate: boolean,
  isChiefMissing: boolean,
  isIndivConflict: boolean,
  cellConflicts: Conflict[],
  isLocked: boolean, // 新增：是否锁定
  onToggleLock: () => void, // 新增：切换锁定
  onUpdate: (type: ShiftType, label?: string) => void,
  onApplySuggestion: (suggestion: ConflictSuggestion) => void,
  onDragStart: () => void,
  onDrop: () => void
}> = ({ record, employeeName, isChiefCandidate, isChiefMissing, isIndivConflict, cellConflicts, isLocked, onToggleLock, onUpdate, onApplySuggestion, onDragStart, onDrop }) => {
  const [isOver, setIsOver] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [showCustomInput, setShowCustomInput] = useState(false);
  const [dropdownAbove, setDropdownAbove] = useState(false);
  const [customText, setCustomText] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const cellRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // 点击外部关闭下拉
  useEffect(() => {
    if (!showDropdown) return;
    const handler = (e: MouseEvent) => {
      if (cellRef.current && !cellRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
        setShowCustomInput(false);
        setCustomText('');
      }
    };
    const scrollHandler = () => {
      setShowDropdown(false);
      setShowCustomInput(false);
      setCustomText('');
    };
    document.addEventListener('mousedown', handler);
    window.addEventListener('scroll', scrollHandler, true);
    return () => {
      document.removeEventListener('mousedown', handler);
      window.removeEventListener('scroll', scrollHandler, true);
    };
  }, [showDropdown]);

  // 自定义输入时自动聚焦
  useEffect(() => {
    if (showCustomInput && inputRef.current) {
      inputRef.current.focus();
    }
  }, [showCustomInput]);

  const colors: Record<ShiftType, string> = {
    [ShiftType.LATE_NIGHT]: 'bg-[#1e3a8a] text-white',
    [ShiftType.MINI_NIGHT]: 'bg-[#3b82f6] text-white',
    [ShiftType.DAY]: 'bg-[#facc15] text-slate-900',
    [ShiftType.SLEEP]: 'bg-[#9ca3af] text-white',
    [ShiftType.VACATION]: 'bg-[#4ade80] text-slate-900',
    [ShiftType.CUSTOM]: 'bg-[#f97316] text-white',
    [ShiftType.NONE]: 'bg-white dark:bg-slate-900 border border-dashed border-slate-200 dark:border-slate-700 text-transparent',
  };

  const labels: Record<ShiftType, string> = {
    [ShiftType.LATE_NIGHT]: '大夜',
    [ShiftType.MINI_NIGHT]: '小夜',
    [ShiftType.DAY]: '白班',
    [ShiftType.SLEEP]: '睡觉',
    [ShiftType.VACATION]: '休假',
    [ShiftType.CUSTOM]: record.label || '自定义',
    [ShiftType.NONE]: '',
  };

  const displayLabel = record.type === ShiftType.CUSTOM ? (record.label || '自定义') : labels[record.type];

  const handleSelect = (type: ShiftType) => {
    if (type === ShiftType.CUSTOM) {
      setShowCustomInput(true);
      setCustomText(record.type === ShiftType.CUSTOM && record.label ? record.label : '');
    } else {
      onUpdate(type);
      setShowDropdown(false);
      setShowCustomInput(false);
    }
  };

  const handleCustomConfirm = () => {
    onUpdate(ShiftType.CUSTOM, customText.trim() || '自定义');
    setShowDropdown(false);
    setShowCustomInput(false);
    setCustomText('');
  };

  const hasError = false; // 冲突统一在右下角冲突详情中显示，单元格内不再标记

  return (
    <div
      ref={cellRef}
      draggable
      onDragStart={() => {
        setIsDragging(true);
        onDragStart();
      }}
      onDragEnd={() => {
        // 延迟重置拖拽状态，避免 onClick 立即触发
        setTimeout(() => setIsDragging(false), 50);
      }}
      onDragOver={(e) => { e.preventDefault(); setIsOver(true); }}
      onDragLeave={() => setIsOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setIsOver(false);
        onDrop();
      }}
      onClick={(e) => {
        e.stopPropagation();
        // 只有在非拖拽状态下才打开下拉
        if (!isDragging && !showDropdown) {
          // 检测下方空间是否足够（下拉菜单约 280px 高）
          if (cellRef.current) {
            const rect = cellRef.current.getBoundingClientRect();
            const spaceBelow = window.innerHeight - rect.bottom;
            const spaceAbove = rect.top;
            // 如果下方空间不足 300px，且上方空间更大，则向上显示
            setDropdownAbove(spaceBelow < 300 && spaceAbove > spaceBelow);
          }
          setShowDropdown(true);
        }
      }}
      className={`h-14 border-r border-b border-slate-100 dark:border-slate-800 flex flex-col items-center justify-center transition-all cursor-pointer select-none relative group
        ${isOver ? 'bg-primary/20 scale-95' : 'hover:bg-slate-50 dark:hover:bg-slate-800/50'}
        ${isChiefCandidate ? 'bg-blue-50/30 dark:bg-blue-900/10 border-l-2 border-l-blue-300 dark:border-l-blue-700' : ''}
        ${isLocked ? 'ring-2 ring-inset ring-green-500/50' : ''}
      `}
    >
      <div className={`w-[54px] h-6 rounded flex items-center justify-center font-bold text-[10px] shadow-sm transition-transform group-hover:scale-110 ${colors[record.type]}`}>
        {displayLabel}
      </div>

      {/* 锁定图标 */}
      {isLocked && (
        <span
          className="material-icons absolute top-1 left-1 text-green-600 dark:text-green-400 text-[14px] cursor-pointer hover:scale-110 transition-transform"
          onClick={(e) => {
            e.stopPropagation();
            onToggleLock();
          }}
          title="点击解锁"
        >
          lock
        </span>
      )}

      {/* 解锁图标（hover时显示） */}
      {!isLocked && (
        <span
          className="material-icons absolute top-1 left-1 text-slate-400 dark:text-slate-500 text-[14px] opacity-0 group-hover:opacity-100 cursor-pointer hover:scale-110 transition-all"
          onClick={(e) => {
            e.stopPropagation();
            onToggleLock();
          }}
          title="点击锁定"
        >
          lock_open
        </span>
      )}

      {record.type === ShiftType.NONE && (
        <div className="absolute inset-0 flex items-center justify-center opacity-10">
          <div className="w-6 h-3 rounded-full border border-slate-400 dark:border-slate-500"></div>
        </div>
      )}

      {/* 下拉选择菜单 */}
      {showDropdown && (
        <div
          className={`fixed z-[9999] bg-white dark:bg-slate-800 rounded-lg shadow-xl border border-slate-200 dark:border-slate-700 py-1 min-w-[90px]`}
          style={{
            left: cellRef.current ? `${cellRef.current.getBoundingClientRect().left + cellRef.current.getBoundingClientRect().width / 2}px` : '0',
            transform: 'translateX(-50%)',
            top: dropdownAbove
              ? cellRef.current ? `${cellRef.current.getBoundingClientRect().top - 8}px` : '0'
              : cellRef.current ? `${cellRef.current.getBoundingClientRect().bottom + 8}px` : '0',
            ...(dropdownAbove && { transform: 'translate(-50%, -100%)' })
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {!showCustomInput ? (
            SHIFT_OPTIONS.map(opt => (
              <button
                key={opt.type}
                onClick={() => handleSelect(opt.type)}
                className={`w-full px-3 py-1.5 text-[11px] font-bold flex items-center gap-2 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors
                  ${record.type === opt.type ? 'bg-slate-50 dark:bg-slate-700/50' : ''}
                `}
              >
                <span className={`inline-block w-4 h-4 rounded ${opt.color} flex-shrink-0`}></span>
                <span className="text-slate-700 dark:text-slate-200">{opt.label}</span>
                {record.type === opt.type && (
                  <span className="material-icons text-primary text-[14px] ml-auto">check</span>
                )}
              </button>
            ))
          ) : (
            <div className="px-2 py-2 flex flex-col gap-2">
              <input
                ref={inputRef}
                value={customText}
                onChange={(e) => setCustomText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleCustomConfirm();
                  if (e.key === 'Escape') { setShowCustomInput(false); setCustomText(''); }
                }}
                placeholder="输入自定义文字"
                className="w-full px-2 py-1.5 text-[11px] border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200 outline-none focus:ring-1 focus:ring-primary"
              />
              <div className="flex gap-1">
                <button
                  onClick={handleCustomConfirm}
                  className="flex-1 px-2 py-1 text-[10px] font-bold bg-primary text-white rounded hover:bg-primary/90 transition-colors"
                >
                  确定
                </button>
                <button
                  onClick={() => { setShowCustomInput(false); setCustomText(''); }}
                  className="flex-1 px-2 py-1 text-[10px] font-bold bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded hover:bg-slate-300 dark:hover:bg-slate-600 transition-colors"
                >
                  取消
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default MatrixGrid;
