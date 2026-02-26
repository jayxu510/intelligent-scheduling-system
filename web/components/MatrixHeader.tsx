
import React, { useState, useRef, useEffect } from 'react';

interface MatrixHeaderProps {
  activeGroup: 'A' | 'B' | 'C';
  onGroupChange: (group: 'A' | 'B' | 'C') => void;
  selectedMonth: string;
  onMonthChange: (val: string) => void;
  onAutoSchedule: () => void;
  onSaveSchedule?: () => void;
  onExportSchedule?: () => void;
  onAddEmployee?: () => void;
  employeeCount?: number;
  isLoading?: boolean;
  isSaving?: boolean;
  isBackendAvailable?: boolean;
}

const MatrixHeader: React.FC<MatrixHeaderProps> = ({
  activeGroup, onGroupChange, selectedMonth, onMonthChange, onAutoSchedule,
  onSaveSchedule, onExportSchedule, onAddEmployee, employeeCount = 0,
  isLoading, isSaving, isBackendAvailable
}) => {
  const [showPicker, setShowPicker] = useState(false);
  const pickerRef = useRef<HTMLDivElement>(null);

  const [currentYear, currentMonth] = selectedMonth.split('-').map(Number);

  // Close picker when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(event.target as Node)) {
        setShowPicker(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleYearChange = (delta: number) => {
    const newYear = currentYear + delta;
    onMonthChange(`${newYear}-${currentMonth.toString().padStart(2, '0')}`);
  };

  const handleMonthSelect = (m: number) => {
    onMonthChange(`${currentYear}-${m.toString().padStart(2, '0')}`);
    setShowPicker(false);
  };

  return (
    <header className="h-14 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between px-6 shrink-0 z-[100]">
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center text-white shadow-sm">
            <span className="material-icons text-lg">grid_view</span>
          </div>
          <h1 className="font-bold text-base text-slate-800 dark:text-slate-100 hidden lg:block tracking-tight">智能排班平台</h1>
          {/* 后端状态指示器 */}
          <div className={`w-2 h-2 rounded-full ${isBackendAvailable ? 'bg-green-500' : 'bg-yellow-500'}`}
               title={isBackendAvailable ? '已连接后端' : '本地模式'} />
        </div>

        {/* Custom Month Picker */}
        <div className="relative" ref={pickerRef}>
          <button
            onClick={() => setShowPicker(!showPicker)}
            className="flex items-center gap-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 transition-all px-4 py-2 rounded-lg font-black text-sm text-slate-700 dark:text-slate-200 shadow-sm border border-transparent active:scale-95 outline-none"
          >
            <span className="material-icons text-slate-400 text-sm">calendar_today</span>
            <span>{currentYear}年 {currentMonth}月</span>
            <span className={`material-icons text-slate-400 text-xs transition-transform ${showPicker ? 'rotate-180' : ''}`}>expand_more</span>
          </button>

          {showPicker && (
            <div className="absolute top-full left-0 mt-2 w-64 bg-white dark:bg-slate-800 rounded-xl shadow-2xl border border-slate-200 dark:border-slate-700 p-4 z-[110] animate-in fade-in zoom-in-95 duration-200">
              <div className="flex items-center justify-between mb-4 pb-2 border-b border-slate-100 dark:border-slate-700">
                <button onClick={() => handleYearChange(-1)} className="p-1 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-md transition-colors">
                  <span className="material-icons text-sm">chevron_left</span>
                </button>
                <div className="flex flex-col items-center">
                  <span className="text-[10px] text-slate-400 font-bold uppercase tracking-widest">选择年份</span>
                  <span className="text-sm font-black text-slate-800 dark:text-slate-100">{currentYear}</span>
                </div>
                <button onClick={() => handleYearChange(1)} className="p-1 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-md transition-colors">
                  <span className="material-icons text-sm">chevron_right</span>
                </button>
              </div>

              <div className="grid grid-cols-3 gap-2">
                {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                  <button
                    key={m}
                    onClick={() => handleMonthSelect(m)}
                    className={`py-2 text-[12px] font-bold rounded-lg transition-all ${
                      m === currentMonth
                        ? 'bg-primary text-white shadow-md shadow-primary/20'
                        : 'text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-700'
                    }`}
                  >
                    {m}月
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <nav className="flex items-center bg-slate-100 dark:bg-slate-800 p-1 rounded-lg">
          {(['A', 'B', 'C'] as const).map(group => (
            <button
              key={group}
              onClick={() => onGroupChange(group)}
              className={`px-4 py-1.5 text-xs font-bold rounded-md transition-all ${
                activeGroup === group
                  ? 'bg-white dark:bg-slate-700 shadow-sm text-primary'
                  : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
              }`}
            >
              {group}组
            </button>
          ))}
        </nav>
      </div>

      <div className="flex items-center gap-6">
        <div className="flex items-center gap-4 border-r border-slate-200 dark:border-slate-700 pr-6 mr-2">
          <LegendItem color="bg-[#facc15]" label="白班" />
          <LegendItem color="bg-[#9ca3af]" label="睡觉" />
          <LegendItem color="bg-[#1e3a8a]" label="大夜" />
          <LegendItem color="bg-[#3b82f6]" label="小夜" />
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={onAutoSchedule}
            disabled={isLoading}
            className={`border border-primary text-primary hover:bg-primary hover:text-white px-4 py-2 rounded-lg text-sm font-bold flex items-center gap-2 transition-all active:scale-95 group ${
              isLoading ? 'opacity-50 cursor-not-allowed' : ''
            }`}
          >
            <span className={`material-icons text-sm ${isLoading ? 'animate-spin' : 'group-hover:rotate-180'} transition-transform duration-500`}>
              {isLoading ? 'sync' : 'auto_awesome'}
            </span>
            {isLoading ? '排班中...' : '智能一键排班'}
          </button>

          <button
            onClick={onExportSchedule}
            disabled={isLoading || !isBackendAvailable}
            className={`border border-emerald-600 text-emerald-600 hover:bg-emerald-600 hover:text-white px-4 py-2 rounded-lg text-sm font-bold flex items-center gap-2 transition-all active:scale-95 group ${
              (isLoading || !isBackendAvailable) ? 'opacity-50 cursor-not-allowed' : ''
            }`}
          >
            <span className="material-icons text-sm">description</span>
            导出Excel
          </button>

          <button
            onClick={onSaveSchedule}
            disabled={isSaving || !isBackendAvailable}
            className={`bg-primary text-white px-4 py-2 rounded-lg text-sm font-bold flex items-center gap-2 shadow-lg shadow-primary/20 transition-all active:scale-95 ${
              (isSaving || !isBackendAvailable) ? 'opacity-50 cursor-not-allowed' : ''
            }`}
          >
            <span className={`material-icons text-sm ${isSaving ? 'animate-pulse' : ''}`}>
              {isSaving ? 'hourglass_top' : 'save'}
            </span>
            {isSaving ? '保存中...' : '保存排班'}
          </button>
        </div>
      </div>
    </header>
  );
};

const LegendItem: React.FC<{ color: string, label: string }> = ({ color, label }) => (
  <div className="flex items-center gap-1.5">
    <div className={`w-3 h-3 rounded-full ${color} shadow-sm border border-black/5`}></div>
    <span className="text-[11px] font-bold text-slate-500 dark:text-slate-400">{label}</span>
  </div>
);

export default MatrixHeader;
