
import React, { useState } from 'react';
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
  onOptimize?: () => void; // 新增：一键优化
  onUndoOptimize?: () => void; // 新增：回退优化
  canUndo?: boolean; // 新增：是否可以回退
}

const MatrixFooter: React.FC<MatrixFooterProps> = ({ stats, conflicts, onOptimize, onUndoOptimize, canUndo = false }) => {
  const [showConflictDetails, setShowConflictDetails] = useState(false);

  const getShiftText = (type?: ShiftType) => {
    switch(type) {
      case ShiftType.SLEEP: return 'SLEEP';
      case ShiftType.MINI_NIGHT: return '小夜';
      case ShiftType.LATE_NIGHT: return '大夜';
      default: return '夜班';
    }
  };

  return (
    <>
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
          {/* 回退按钮 */}
          {canUndo && (
            <button
              onClick={onUndoOptimize}
              className="px-4 py-2 bg-slate-100 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg flex items-center gap-2 hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
              title="回退到优化前的状态"
            >
              <span className="material-icons text-slate-600 dark:text-slate-300 text-[18px]">undo</span>
              <span className="text-[11px] text-slate-700 dark:text-slate-200 font-bold">
                回退优化
              </span>
            </button>
          )}

          {conflicts.length > 0 ? (
            <button
              onClick={() => setShowConflictDetails(true)}
              className="px-4 py-2 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/30 rounded-lg flex items-center gap-3 animate-in fade-in slide-in-from-bottom-2 duration-300 hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors cursor-pointer"
            >
              <span className="material-symbols-outlined text-red-500 text-[20px] font-black">warning</span>
              <div className="flex flex-col">
                <span className="text-[11px] text-red-700 dark:text-red-400 font-black leading-tight uppercase">
                  发现 {conflicts.length} 个冲突
                </span>
                <span className="text-[9px] text-red-400 font-medium">
                  点击查看详情
                </span>
              </div>
            </button>
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

      {/* 冲突详情弹窗 */}
      {showConflictDetails && (
        <div
          className="fixed inset-0 bg-black/50 z-[200] flex items-center justify-center"
          onClick={() => setShowConflictDetails(false)}
        >
          <div
            className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl border border-slate-200 dark:border-slate-700 w-[600px] max-h-[80vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* 标题栏 */}
            <div className="flex items-center justify-between p-6 border-b border-slate-200 dark:border-slate-700">
              <div className="flex items-center gap-3">
                <span className="material-icons text-red-500 text-2xl">error</span>
                <div>
                  <h3 className="text-lg font-black text-slate-800 dark:text-slate-100">冲突详情</h3>
                  <p className="text-sm text-slate-500 dark:text-slate-400">共发现 {conflicts.length} 个冲突</p>
                </div>
              </div>
              <button
                onClick={() => setShowConflictDetails(false)}
                className="p-2 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
              >
                <span className="material-icons text-slate-400">close</span>
              </button>
            </div>

            {/* 冲突列表 */}
            <div className="flex-1 overflow-y-auto p-6 space-y-3">
              {conflicts.map((conflict, idx) => (
                <div
                  key={idx}
                  className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/30 rounded-lg"
                >
                  <div className="flex items-start gap-3">
                    <span className="material-icons text-red-500 text-xl mt-0.5">warning</span>
                    <div className="flex-1">
                      <div className="text-sm font-bold text-red-700 dark:text-red-400 mb-1">
                        {conflict.date} {conflict.shiftType && `- ${getShiftText(conflict.shiftType)}`}
                      </div>
                      <div className="text-sm text-slate-700 dark:text-slate-300">
                        {conflict.message}
                      </div>
                      {conflict.employeeIds.length > 0 && (
                        <div className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                          涉及员工: {conflict.employeeIds.join(', ')}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* 操作按钮 */}
            <div className="p-6 border-t border-slate-200 dark:border-slate-700 flex gap-3">
              <button
                onClick={() => {
                  onOptimize?.();
                  setShowConflictDetails(false);
                }}
                className="flex-1 px-4 py-3 bg-blue-500 text-white rounded-lg font-bold hover:bg-blue-600 transition-colors flex items-center justify-center gap-2"
              >
                <span className="material-icons text-xl">auto_fix_high</span>
                一键优化（当日及以后）
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

const StatItem: React.FC<{ label: string; value: string; valueColor?: string }> = ({ label, value, valueColor = 'text-slate-800 dark:text-slate-100' }) => (
  <div className="flex flex-col">
    <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">{label}</span>
    <span className={`text-base font-black ${valueColor}`}>{value}</span>
  </div>
);

export default MatrixFooter;
