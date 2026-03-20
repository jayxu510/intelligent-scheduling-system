import React, { useEffect, useMemo, useRef, useState } from 'react';

type ShiftVisual = {
  id: string;
  label: string;
  className: string;
};

interface SolverConvergenceLoadingProps {
  employeesCount?: number;
  rowsCount?: number;
}

const SHIFT_VISUALS: ShiftVisual[] = [
  { id: 'DAY', label: '白', className: 'bg-[#facc15] text-slate-900' },
  { id: 'MINI_NIGHT', label: '小', className: 'bg-[#3b82f6] text-white' },
  { id: 'LATE_NIGHT', label: '大', className: 'bg-[#1e3a8a] text-white' },
  { id: 'SLEEP', label: '睡', className: 'bg-[#9ca3af] text-white' },
  { id: 'VACATION', label: '休', className: 'bg-[#4ade80] text-slate-900' },
];

const pickRandomShift = () => SHIFT_VISUALS[Math.floor(Math.random() * SHIFT_VISUALS.length)];

const SolverConvergenceLoading: React.FC<SolverConvergenceLoadingProps> = ({
  employeesCount = 8,
  rowsCount = 14,
}) => {
  const employeeCols = useMemo(() => Math.min(12, Math.max(6, employeesCount)), [employeesCount]);
  const scheduleRows = useMemo(() => Math.min(20, Math.max(10, rowsCount)), [rowsCount]);

  const totalCells = employeeCols * scheduleRows;

  const [cellState, setCellState] = useState<ShiftVisual[]>(() =>
    Array.from({ length: totalCells }, () => pickRandomShift())
  );
  const [lockedCells, setLockedCells] = useState<Set<number>>(new Set());
  const [comboCount, setComboCount] = useState(14205);
  const [displayProgress, setDisplayProgress] = useState(0);

  const lockCursorRef = useRef(0);
  const lockOrderRef = useRef<number[]>([]);
  const countRef = useRef(14205);

  useEffect(() => {
    const order = Array.from({ length: totalCells }, (_, idx) => idx).sort((a, b) => {
      const rowA = Math.floor(a / employeeCols);
      const colA = a % employeeCols;
      const rowB = Math.floor(b / employeeCols);
      const colB = b % employeeCols;

      const scoreA = rowA * 3 + colA + Math.random() * 1.5;
      const scoreB = rowB * 3 + colB + Math.random() * 1.5;
      return scoreA - scoreB;
    });

    lockOrderRef.current = order;
    lockCursorRef.current = 0;
    setLockedCells(new Set());
    setDisplayProgress(0);
    setCellState(Array.from({ length: totalCells }, () => pickRandomShift()));
  }, [totalCells, employeeCols]);

  useEffect(() => {
    const flickerTimer = window.setInterval(() => {
      setCellState(prev => {
        const next = [...prev];

        for (let i = 0; i < totalCells; i += 1) {
          if (lockedCells.has(i)) continue;
          if (Math.random() < 0.82) {
            next[i] = pickRandomShift();
          }
        }

        return next;
      });
    }, 130);

    return () => window.clearInterval(flickerTimer);
  }, [lockedCells, totalCells]);

  useEffect(() => {
    const lockTimer = window.setInterval(() => {
      setLockedCells(prev => {
        if (prev.size >= totalCells) return prev;

        const next = new Set(prev);
        const progress = next.size / Math.max(1, totalCells);
        const batch = Math.max(4, Math.floor(employeeCols * (0.4 + progress * 1.2)));

        for (let i = 0; i < batch && lockCursorRef.current < lockOrderRef.current.length; i += 1) {
          next.add(lockOrderRef.current[lockCursorRef.current]);
          lockCursorRef.current += 1;
        }

        return next;
      });
    }, 1500);

    return () => window.clearInterval(lockTimer);
  }, [employeeCols, totalCells]);

  useEffect(() => {
    let rafId = 0;
    let last = performance.now();

    const tick = (now: number) => {
      const dt = now - last;
      last = now;

      const lockRatio = lockedCells.size / Math.max(1, totalCells);
      const speed = 220 + (1 - lockRatio) * 950;
      countRef.current += Math.floor((dt / 1000) * speed);

      setComboCount(countRef.current);
      rafId = window.requestAnimationFrame(tick);
    };

    rafId = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(rafId);
  }, [lockedCells.size, totalCells]);

  useEffect(() => {
    const durationMs = 120000;
    const start = performance.now();

    const timer = window.setInterval(() => {
      const elapsed = performance.now() - start;
      const linear = Math.min(1, elapsed / durationMs);

      // 先快后慢的收敛曲线：在 2 分钟左右逼近并到达 99%
      const eased = 1 - Math.pow(1 - linear, 1.25);
      const next = Math.min(99, Math.floor(eased * 99));

      setDisplayProgress(next);
    }, 250);

    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="relative h-full w-full overflow-hidden rounded-2xl border border-slate-700 bg-slate-950 shadow-[0_20px_60px_rgba(2,6,23,0.6)]">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_12%,rgba(56,189,248,0.22),transparent_38%),radial-gradient(circle_at_80%_82%,rgba(59,130,246,0.2),transparent_42%)]" />

      <div className="relative z-10 grid h-full" style={{ gridTemplateRows: '48px 1fr' }}>
        <div
          className="grid border-b border-cyan-500/20 bg-slate-900/70"
          style={{ gridTemplateColumns: `64px repeat(${employeeCols}, minmax(56px, 1fr)) 40px 120px 56px` }}
        >
          {Array.from({ length: employeeCols + 4 }).map((_, idx) => (
            <div key={`header-${idx}`} className="border-r border-cyan-500/10 bg-cyan-300/10" />
          ))}
        </div>

        <div
          className="grid"
          style={{
            gridTemplateColumns: `64px repeat(${employeeCols}, minmax(56px, 1fr)) 40px 120px 56px`,
            gridTemplateRows: `repeat(${scheduleRows}, minmax(40px, 1fr))`,
          }}
        >
          {Array.from({ length: scheduleRows }).map((_, rowIdx) => (
            <React.Fragment key={`row-${rowIdx}`}>
              <div className="border-r border-b border-cyan-500/10 bg-cyan-200/10" />

              {Array.from({ length: employeeCols }).map((__, colIdx) => {
                const index = rowIdx * employeeCols + colIdx;
                const shift = cellState[index] || SHIFT_VISUALS[0];
                const isLocked = lockedCells.has(index);

                return (
                  <div
                    key={`cell-${rowIdx}-${colIdx}`}
                    className="flex items-center justify-center border-r border-b border-cyan-500/10"
                  >
                    <div
                      className={`h-5 w-11 rounded-md text-[10px] font-black leading-5 text-center transition-all duration-150 ${shift.className} ${
                        isLocked ? 'opacity-95 shadow-[0_0_0_1px_rgba(15,23,42,0.22)]' : 'opacity-90'
                      }`}
                    >
                      {shift.label}
                    </div>
                  </div>
                );
              })}

              <div className="border-r border-b border-cyan-500/10 bg-cyan-200/10" />
              <div className="border-r border-b border-cyan-500/10 bg-cyan-200/10" />
              <div className="border-b border-cyan-500/10 bg-cyan-200/10" />
            </React.Fragment>
          ))}
        </div>
      </div>

      <div className="pointer-events-none absolute inset-0 z-20">
        <div className="convergence-scan absolute left-0 right-0 h-24" />
      </div>

      <div className="absolute left-1/2 top-1/2 z-30 w-[360px] max-w-[88%] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-cyan-200/25 bg-slate-900/65 p-4 text-center shadow-2xl backdrop-blur-md">
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.25em] text-cyan-300/80">Engine Convergence</div>
        <div className="convergence-number text-2xl font-black text-cyan-100">
          尝试排班组合: {comboCount.toLocaleString('en-US')}
        </div>
        <div className="mt-2 text-xs text-cyan-100/80">正在收敛最优解，请稍候...</div>

        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-cyan-950/80">
          <div
            className="h-full rounded-full bg-gradient-to-r from-cyan-400 via-sky-300 to-blue-400 transition-all duration-500"
            style={{ width: `${displayProgress}%` }}
          />
        </div>
        <div className="mt-1 text-[10px] text-cyan-100/70">收敛进度: {displayProgress}%</div>
      </div>

      <style>{`
        @keyframes convergenceScan {
          0% {
            transform: translateY(-140%);
            opacity: 0;
          }
          10% {
            opacity: 1;
          }
          90% {
            opacity: 1;
          }
          100% {
            transform: translateY(1200%);
            opacity: 0;
          }
        }

        @keyframes pulseNumber {
          0%,
          100% {
            opacity: 0.9;
            text-shadow: 0 0 10px rgba(34, 211, 238, 0.25);
          }
          50% {
            opacity: 1;
            text-shadow: 0 0 18px rgba(34, 211, 238, 0.65);
          }
        }

        .convergence-scan {
          animation: convergenceScan 3.2s linear infinite;
          background: linear-gradient(
            to bottom,
            rgba(34, 211, 238, 0),
            rgba(34, 211, 238, 0.2) 18%,
            rgba(125, 211, 252, 0.9) 50%,
            rgba(34, 211, 238, 0.2) 82%,
            rgba(34, 211, 238, 0)
          );
          box-shadow:
            0 0 20px rgba(34, 211, 238, 0.55),
            0 0 44px rgba(14, 116, 144, 0.45);
          mix-blend-mode: screen;
        }

        .convergence-number {
          animation: pulseNumber 1.4s ease-in-out infinite;
        }
      `}</style>
    </div>
  );
};

export default SolverConvergenceLoading;
