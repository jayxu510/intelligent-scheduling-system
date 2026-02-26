
import React from 'react';
import { Conflict, ShiftType } from '../types';

interface MatrixFooterProps {
  stats: {
    period: string;
    totalHours: number;
    personnelCount: number;
    conflictRate: number;
    targetRate: number;
  };
  conflicts: Conflict[];
}

const MatrixFooter: React.FC<MatrixFooterProps> = ({ stats, conflicts }) => {
  const latestConflict = conflicts.length > 0 ? conflicts[0] : null;

  const getShiftText = (type?: ShiftType) => {
    switch(type) {
      case ShiftType.SLEEP: return 'SLEEP';
      case ShiftType.MINI_NIGHT: return '小夜';
      case ShiftType.LATE_NIGHT: return '大夜';
      default: return '夜班';
    }
  };

  return (
    <footer className="h-16 bg-white dark:bg-slate-900 border-t border-slate-200 dark:border-slate-800 flex items-center px-6 shrink-0 gap-8 shadow-[0_-4px_20px_-5px_rgba(0,0,0,0.1)] z-[60]">
      <div className="flex flex-col">
        <h3 className="text-[10px] font-black text-slate-400 tracking-widest uppercase">全月实况统计</h3>
        <span className="text-xs font-bold text-slate-600 dark:text-slate-300">{stats.period}</span>
      </div>

      <div className="flex items-center gap-8">
        <div className="flex flex-col gap-1 min-w-[160px]">
          <div className="flex justify-between text-[11px] font-bold">
            <span className="text-slate-500">平均月度工时</span>
            <span className="text-primary">{stats.totalHours}h / 人</span>
          </div>
          <div className="h-2 w-full bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden shadow-inner">
            <div 
              className="h-full bg-primary rounded-full transition-all duration-500 ease-out shadow-sm shadow-primary/40" 
              style={{ width: `${Math.min(100, (stats.totalHours / 160) * 100)}%` }}
            ></div>
          </div>
        </div>

        <div className="flex items-center gap-6 border-l border-slate-200 dark:border-slate-700 pl-8">
          <StatItem label="执勤总人数" value={`${stats.personnelCount}人`} />
          <StatItem 
            label="实时冲突数" 
            value={`${conflicts.length}`} 
            valueColor={conflicts.length > 0 ? "text-red-500" : "text-emerald-500"} 
          />
          <StatItem 
            label="定员达标率" 
            value={`${stats.targetRate}%`} 
            valueColor="text-emerald-500" 
          />
        </div>
      </div>

      <div className="ml-auto flex items-center gap-3">
        {conflicts.length > 0 ? (
          <div className="px-4 py-2 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/30 rounded-lg flex items-center gap-3 animate-in fade-in slide-in-from-bottom-2 duration-300">
            <span className="material-symbols-outlined text-red-500 text-[20px] font-black">warning</span>
            <div className="flex flex-col">
              <span className="text-[11px] text-red-700 dark:text-red-400 font-black leading-tight uppercase">
                {latestConflict?.date.slice(-2)}日 {getShiftText(latestConflict?.shiftType)} 存在多个主任席
              </span>
              {conflicts.length > 1 && (
                <span className="text-[9px] text-red-400 font-medium">
                  还有 {conflicts.length - 1} 个冲突待处理...
                </span>
              )}
            </div>
          </div>
        ) : (
          <div className="px-4 py-2 bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-100 dark:border-emerald-900/30 rounded-lg flex items-center gap-2">
            <span className="material-icons text-emerald-500 text-sm">check_circle</span>
            <span className="text-[11px] text-emerald-700 dark:text-emerald-400 font-bold">
              排班无冲突，方案合规
            </span>
          </div>
        )}
      </div>
    </footer>
  );
};

const StatItem: React.FC<{ label: string; value: string; valueColor?: string }> = ({ label, value, valueColor = 'text-slate-800 dark:text-slate-100' }) => (
  <div className="flex flex-col">
    <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">{label}</span>
    <span className={`text-base font-black ${valueColor}`}>{value}</span>
  </div>
);

export default MatrixFooter;
