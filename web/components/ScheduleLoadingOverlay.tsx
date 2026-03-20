import React, { useEffect, useMemo, useState } from 'react';

interface ScheduleLoadingOverlayProps {
  employeesCount?: number;
  rowsCount?: number;
}

const loadingMessages = [
  '🔍 正在读取上月历史排班数据，进行跨月追溯...',
  '🧮 正在构建 16 天时空滑动窗口，建立约束模型...',
  '⚖️ 正在执行大夜班防断档与连续白班防密集校验...',
  '💯 正在进入疲劳度积分拍卖场，优化白班分配...',
  '🔄 正在尝试第 13,042 种组合，寻求全局最优解...',
  '✨ 数学模型计算接近尾声，正在校验最终公平性...',
];

const ScheduleLoadingOverlay: React.FC<ScheduleLoadingOverlayProps> = ({
  employeesCount = 8,
  rowsCount = 14,
}) => {
  const [messageIndex, setMessageIndex] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setMessageIndex((prev) => (prev + 1) % loadingMessages.length);
    }, 4000);

    return () => {
      window.clearInterval(timer);
    };
  }, []);

  const employeeColumns = useMemo(() => {
    return Math.min(12, Math.max(6, employeesCount));
  }, [employeesCount]);

  const skeletonRows = useMemo(() => {
    return Math.min(18, Math.max(10, rowsCount));
  }, [rowsCount]);

  return (
    <div className="relative h-full w-full overflow-hidden rounded-2xl border border-cyan-200/40 bg-slate-950 p-3 shadow-[0_0_0_1px_rgba(34,211,238,0.12),0_20px_60px_rgba(2,6,23,0.7)]">
      <div className="mb-3 rounded-xl border border-cyan-300/20 bg-slate-900/80 px-4 py-3 backdrop-blur-sm">
        <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.25em] text-cyan-300/80">
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-cyan-300" />
          AI Scheduling Engine
        </div>
        <p className="schedule-loading-message min-h-6 text-sm font-semibold text-cyan-100">
          {loadingMessages[messageIndex]}
        </p>
      </div>

      <div className="relative h-[calc(100%-92px)] overflow-hidden rounded-xl border border-cyan-400/20 bg-slate-900/70">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(34,211,238,0.15),transparent_40%),radial-gradient(circle_at_80%_80%,rgba(59,130,246,0.18),transparent_45%)]" />

        <div
          className="relative grid border-b border-cyan-400/15"
          style={{
            gridTemplateColumns: `64px repeat(${employeeColumns}, minmax(56px, 1fr)) 40px 120px 56px`,
          }}
        >
          {Array.from({ length: employeeColumns + 4 }).map((_, index) => (
            <div
              key={`header-${index}`}
              className="h-11 animate-pulse border-r border-cyan-400/10 bg-cyan-200/10"
            />
          ))}
        </div>

        <div
          className="relative grid"
          style={{
            gridTemplateColumns: `64px repeat(${employeeColumns}, minmax(56px, 1fr)) 40px 120px 56px`,
          }}
        >
          {Array.from({ length: skeletonRows }).map((_, rowIdx) => (
            <React.Fragment key={`row-${rowIdx}`}>
              <div className="h-10 border-r border-b border-cyan-400/10 bg-cyan-200/10 p-2">
                <div className="h-full w-full animate-pulse rounded bg-cyan-100/20" />
              </div>

              {Array.from({ length: employeeColumns }).map((__, colIdx) => (
                <div
                  key={`cell-${rowIdx}-${colIdx}`}
                  className="flex h-10 items-center justify-center border-r border-b border-cyan-400/10"
                >
                  <div className="h-5 w-10 animate-pulse rounded-md bg-cyan-100/20" />
                </div>
              ))}

              <div className="flex h-10 items-center justify-center border-r border-b border-cyan-400/10">
                <div className="h-5 w-5 animate-pulse rounded-full bg-cyan-100/20" />
              </div>

              <div className="h-10 border-r border-b border-cyan-400/10 p-2">
                <div className="grid h-full grid-cols-2 gap-1">
                  {Array.from({ length: 4 }).map((__, statIdx) => (
                    <div key={`stat-${rowIdx}-${statIdx}`} className="animate-pulse rounded bg-cyan-100/20" />
                  ))}
                </div>
              </div>

              <div className="flex h-10 items-center justify-center border-b border-cyan-400/10">
                <div className="h-5 w-5 animate-pulse rounded bg-cyan-100/20" />
              </div>
            </React.Fragment>
          ))}
        </div>

        <div className="radar-scan-line absolute left-0 right-0 h-20" />
      </div>

      <style>{`
        @keyframes radarScan {
          0% {
            transform: translateY(-120%);
            opacity: 0;
          }
          8% {
            opacity: 1;
          }
          92% {
            opacity: 1;
          }
          100% {
            transform: translateY(1050%);
            opacity: 0;
          }
        }

        @keyframes messageBreath {
          0%, 100% {
            opacity: 0.7;
          }
          50% {
            opacity: 1;
          }
        }

        .radar-scan-line {
          animation: radarScan 3.8s linear infinite;
          background: linear-gradient(
            to bottom,
            rgba(56, 189, 248, 0),
            rgba(56, 189, 248, 0.2) 20%,
            rgba(125, 211, 252, 0.85) 50%,
            rgba(56, 189, 248, 0.2) 80%,
            rgba(56, 189, 248, 0)
          );
          box-shadow:
            0 0 18px rgba(56, 189, 248, 0.65),
            0 0 36px rgba(14, 116, 144, 0.5);
          mix-blend-mode: screen;
          pointer-events: none;
        }

        .schedule-loading-message {
          animation: messageBreath 2.4s ease-in-out infinite;
        }
      `}</style>
    </div>
  );
};

export default ScheduleLoadingOverlay;
