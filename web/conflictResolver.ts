import { Conflict, ConflictSuggestion, ShiftType, DailySchedule, Employee } from './types';

// 实际工作班次
const WORK_SHIFTS = [ShiftType.DAY, ShiftType.SLEEP, ShiftType.MINI_NIGHT, ShiftType.LATE_NIGHT];

// 标准定员要求
const STD_REQUIREMENTS: Record<string, number> = {
  [ShiftType.DAY]: 6,
  [ShiftType.SLEEP]: 5,
  [ShiftType.MINI_NIGHT]: 3,
  [ShiftType.LATE_NIGHT]: 3,
};

/**
 * 获取今天的日期字符串 YYYY-MM-DD
 */
function getTodayStr(): string {
  const now = new Date();
  const y = now.getFullYear();
  const m = (now.getMonth() + 1).toString().padStart(2, '0');
  const d = now.getDate().toString().padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/**
 * 获取当天各班次实际要求（考虑白班特殊规则）
 */
function getDayRequirements(schedule: DailySchedule): Record<string, number> {
  const hasVC = schedule.records.some(
    r => r.type === ShiftType.VACATION || r.type === ShiftType.CUSTOM
  );
  return {
    ...STD_REQUIREMENTS,
    [ShiftType.DAY]: hasVC ? 5 : 6,
  };
}

/**
 * 获取当天各班次实际人数
 */
function getShiftCounts(schedule: DailySchedule): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const shift of WORK_SHIFTS) {
    counts[shift] = schedule.records.filter(r => r.type === shift).length;
  }
  return counts;
}

/**
 * 为冲突生成调整建议
 * @param lockedCells 用户手动修改过的单元格，建议不能动这些
 */
export function generateConflictSuggestion(
  conflict: Conflict,
  schedules: DailySchedule[],
  employees: Employee[],
  lockedCells: Set<string> = new Set()
): ConflictSuggestion | null {
  const today = getTodayStr();

  // 只建议修改当天和以后的排班，过去的不管
  if (conflict.date < today) return null;

  const empMap = new Map(employees.map(e => [e.id, e]));

  switch (conflict.type) {
    case 'SLOT_COUNT_MISMATCH':
      return generateSlotCountSuggestion(conflict, schedules, empMap, lockedCells);

    case 'CONSECUTIVE_VIOLATION':
      return generateConsecutiveSuggestion(conflict, schedules, empMap, lockedCells);

    case 'CHIEF_MISSING':
      return generateChiefMissingSuggestion(conflict, schedules, empMap, lockedCells);

    case 'CHIEF_DUPLICATE':
      return generateChiefDuplicateSuggestion(conflict, schedules, empMap, lockedCells);

    default:
      return null;
  }
}

/**
 * 检查单元格是否被用户锁定
 */
function isCellLocked(lockedCells: Set<string>, date: string, employeeId: string): boolean {
  return lockedCells.has(`${date}:${employeeId}`);
}

/**
 * 定员冲突调整建议
 * 核心：只在超员和缺员的班次之间互相调剂，保证不破坏其他班次定员
 */
function generateSlotCountSuggestion(
  conflict: Conflict,
  schedules: DailySchedule[],
  empMap: Map<string, Employee>,
  lockedCells: Set<string>
): ConflictSuggestion | null {
  const schedule = schedules.find(s => s.date === conflict.date);
  if (!schedule || !conflict.shiftType) return null;

  const shiftType = conflict.shiftType;
  const counts = getShiftCounts(schedule);
  const reqs = getDayRequirements(schedule);

  const currentCount = counts[shiftType] || 0;
  const required = reqs[shiftType] || 0;

  if (currentCount === required) return null;

  const changes: ConflictSuggestion['changes'] = [];

  if (currentCount > required) {
    // 超员：找缺员的班次，配对调剂
    const excess = currentCount - required;
    const underStaffed = WORK_SHIFTS.filter(
      s => s !== shiftType && (counts[s] || 0) < (reqs[s] || 0)
    );

    let moved = 0;
    const sourceRecords = schedule.records.filter(
      r => r.type === shiftType && !isCellLocked(lockedCells, schedule.date, r.employeeId)
    );

    for (const targetShift of underStaffed) {
      if (moved >= excess) break;
      const targetShortage = (reqs[targetShift] || 0) - (counts[targetShift] || 0);
      const toMove = Math.min(excess - moved, targetShortage);

      for (let i = 0; i < toMove && moved + i < sourceRecords.length; i++) {
        const rec = sourceRecords[moved + i];
        changes.push({
          date: schedule.date,
          employeeId: rec.employeeId,
          fromType: shiftType,
          toType: targetShift,
          employeeName: empMap.get(rec.employeeId)?.name
        });
      }
      moved += toMove;
    }

    if (changes.length > 0) {
      return {
        description: `${getShiftName(shiftType)}超员${excess}人，调剂至缺员班次`,
        changes
      };
    }
  } else {
    // 缺员：从超员的班次拉人
    const shortage = required - currentCount;
    const overStaffed = WORK_SHIFTS.filter(
      s => s !== shiftType && (counts[s] || 0) > (reqs[s] || 0)
    );

    let pulled = 0;
    for (const sourceShift of overStaffed) {
      if (pulled >= shortage) break;
      const sourceExcess = (counts[sourceShift] || 0) - (reqs[sourceShift] || 0);
      const toPull = Math.min(shortage - pulled, sourceExcess);
      const sourceRecords = schedule.records.filter(
        r => r.type === sourceShift && !isCellLocked(lockedCells, schedule.date, r.employeeId)
      );

      for (let i = 0; i < toPull && i < sourceRecords.length; i++) {
        const rec = sourceRecords[i];
        changes.push({
          date: schedule.date,
          employeeId: rec.employeeId,
          fromType: sourceShift,
          toType: shiftType,
          employeeName: empMap.get(rec.employeeId)?.name
        });
      }
      pulled += toPull;
    }

    if (changes.length > 0) {
      return {
        description: `${getShiftName(shiftType)}缺员${shortage}人，从超员班次调入`,
        changes
      };
    }
  }

  // 没有互补的超员/缺员可调剂
  return null;
}

/**
 * 连续班次冲突调整建议
 * 核心：用 SWAP（互换）两个员工的班次，保证所有班次定员不变
 */
function generateConsecutiveSuggestion(
  conflict: Conflict,
  schedules: DailySchedule[],
  empMap: Map<string, Employee>,
  lockedCells: Set<string>
): ConflictSuggestion | null {
  if (conflict.employeeIds.length === 0 || !conflict.shiftType) return null;

  const today = getTodayStr();
  const empId = conflict.employeeIds[0];
  const empName = empMap.get(empId)?.name || empId;

  // 白班和睡觉班允许连续
  if (conflict.shiftType === ShiftType.DAY || conflict.shiftType === ShiftType.SLEEP) {
    return null;
  }

  // 找到连续的两天，在第二天做互换
  const sorted = [...schedules].sort((a, b) => a.date.localeCompare(b.date));
  const dateIdx = sorted.findIndex(s => s.date === conflict.date);
  if (dateIdx === -1 || dateIdx + 1 >= sorted.length) return null;

  const nextSchedule = sorted[dateIdx + 1];

  // 第二天已过去，不建议
  if (nextSchedule.date < today) return null;

  // 确认该员工在第二天确实是同类班次
  const empNextDayRec = nextSchedule.records.find(r => r.employeeId === empId);
  if (!empNextDayRec || empNextDayRec.type !== conflict.shiftType) return null;

  // 如果冲突员工在第二天的单元格被用户锁定，不建议修改
  if (isCellLocked(lockedCells, nextSchedule.date, empId)) return null;

  // 构建各天各员工的班次查询表
  const shiftLookup = new Map<string, Map<string, ShiftType>>();
  sorted.forEach(s => {
    const m = new Map<string, ShiftType>();
    s.records.forEach(r => m.set(r.employeeId, r.type));
    shiftLookup.set(s.date, m);
  });

  // 在第二天找一个合适的 SWAP 对象
  // 优先从白班找（人数最多 6 人，最灵活），然后睡觉班，最后其他
  const swapShiftOrder = [ShiftType.DAY, ShiftType.SLEEP, ShiftType.MINI_NIGHT, ShiftType.LATE_NIGHT]
    .filter(s => s !== conflict.shiftType);

  for (const candidateShift of swapShiftOrder) {
    const candidates = nextSchedule.records.filter(r =>
      r.employeeId !== empId && r.type === candidateShift
      && !isCellLocked(lockedCells, nextSchedule.date, r.employeeId)
    );

    for (const candidate of candidates) {
      const cId = candidate.employeeId;

      // 检查 swap 后是否给 candidate 造成新的连续冲突
      // candidate 在 nextDay 会变成 conflict.shiftType（小夜或大夜，不允许连续）
      {
        // 检查 candidate 前一天是否也是 conflict.shiftType
        const prevMap = shiftLookup.get(conflict.date);
        if (prevMap?.get(cId) === conflict.shiftType) continue;

        // 检查 candidate 后一天是否也是 conflict.shiftType
        if (dateIdx + 2 < sorted.length) {
          const nextNextMap = shiftLookup.get(sorted[dateIdx + 2].date);
          if (nextNextMap?.get(cId) === conflict.shiftType) continue;
        }
      }

      // 检查 swap 后是否给 empId 造成新的连续冲突
      // empId 在 nextDay 会变成 candidateShift
      if (candidateShift !== ShiftType.DAY && candidateShift !== ShiftType.SLEEP) {
        // 检查 empId 后一天是否也是 candidateShift
        if (dateIdx + 2 < sorted.length) {
          const nextNextMap = shiftLookup.get(sorted[dateIdx + 2].date);
          if (nextNextMap?.get(empId) === candidateShift) continue;
        }
      }

      // 合法的 swap 找到了！
      const cName = empMap.get(cId)?.name || cId;
      return {
        description: `${empName}连续${getShiftName(conflict.shiftType)}，建议${nextSchedule.date.slice(5)}与${cName}互换`,
        changes: [
          {
            date: nextSchedule.date,
            employeeId: empId,
            fromType: conflict.shiftType,
            toType: candidateShift,
            employeeName: empName
          },
          {
            date: nextSchedule.date,
            employeeId: cId,
            fromType: candidateShift,
            toType: conflict.shiftType,
            employeeName: cName
          }
        ]
      };
    }
  }

  // 找不到合法的 swap 对象
  return null;
}

/**
 * 主任席缺失调整建议
 * 核心：SWAP 一个主任（从其他班次）与该班次的一个普通员工互换，定员不变
 */
function generateChiefMissingSuggestion(
  conflict: Conflict,
  schedules: DailySchedule[],
  empMap: Map<string, Employee>,
  lockedCells: Set<string>
): ConflictSuggestion | null {
  const schedule = schedules.find(s => s.date === conflict.date);
  if (!schedule || !conflict.shiftType) return null;

  const leaderIds = Array.from(empMap.values())
    .filter((_, idx) => idx < 6)
    .map(e => e.id);

  const targetShift = conflict.shiftType;

  // 找一个在其他工作班次上的主任
  const swapShiftOrder = [ShiftType.DAY, ShiftType.SLEEP, ShiftType.MINI_NIGHT, ShiftType.LATE_NIGHT]
    .filter(s => s !== targetShift);

  for (const sourceShift of swapShiftOrder) {
    // 找该班次上的主任（排除被用户锁定的）
    const leadersOnSource = schedule.records.filter(
      r => leaderIds.includes(r.employeeId) && r.type === sourceShift
        && !isCellLocked(lockedCells, schedule.date, r.employeeId)
    );

    // 如果源班次只有一个主任，且源班次是夜班，不能把唯一的主任抽走
    const nightShifts = [ShiftType.SLEEP, ShiftType.MINI_NIGHT, ShiftType.LATE_NIGHT];
    if (nightShifts.includes(sourceShift) && leadersOnSource.length <= 1) {
      continue; // 不能把唯一的夜班主任抽走
    }

    if (leadersOnSource.length === 0) continue;

    // 选择一个主任去 targetShift
    const leaderToMove = leadersOnSource[leadersOnSource.length - 1]; // 取最后一个（如果源班次有多个主任）

    // 找 targetShift 上的一个非主任员工来互换（排除被用户锁定的）
    const nonLeadersOnTarget = schedule.records.filter(
      r => !leaderIds.includes(r.employeeId) && r.type === targetShift
        && !isCellLocked(lockedCells, schedule.date, r.employeeId)
    );

    if (nonLeadersOnTarget.length === 0) continue;

    const staffToMove = nonLeadersOnTarget[0];

    return {
      description: `${getShiftName(targetShift)}缺少主任席，建议与${getShiftName(sourceShift)}互换`,
      changes: [
        {
          date: schedule.date,
          employeeId: leaderToMove.employeeId,
          fromType: sourceShift,
          toType: targetShift,
          employeeName: empMap.get(leaderToMove.employeeId)?.name
        },
        {
          date: schedule.date,
          employeeId: staffToMove.employeeId,
          fromType: targetShift,
          toType: sourceShift,
          employeeName: empMap.get(staffToMove.employeeId)?.name
        }
      ]
    };
  }

  return null;
}

/**
 * 主任席重复调整建议
 * 核心：把多余的主任 SWAP 到缺主任的夜班或白班，与该班次的非主任互换
 */
function generateChiefDuplicateSuggestion(
  conflict: Conflict,
  schedules: DailySchedule[],
  empMap: Map<string, Employee>,
  lockedCells: Set<string>
): ConflictSuggestion | null {
  const schedule = schedules.find(s => s.date === conflict.date);
  if (!schedule || !conflict.shiftType) return null;

  const leaderIds = Array.from(empMap.values())
    .filter((_, idx) => idx < 6)
    .map(e => e.id);

  const sourceShift = conflict.shiftType;
  const leadersInShift = schedule.records.filter(
    r => leaderIds.includes(r.employeeId) && r.type === sourceShift
  );

  if (leadersInShift.length <= 1) return null;

  // 多余的主任们（保留第一个，排除被用户锁定的）
  const excessLeaders = leadersInShift.slice(1).filter(
    r => !isCellLocked(lockedCells, schedule.date, r.employeeId)
  );

  // 找目标班次：优先缺主任的夜班，否则白班
  const nightShifts = [ShiftType.SLEEP, ShiftType.MINI_NIGHT, ShiftType.LATE_NIGHT];
  const targetOptions: ShiftType[] = [];

  for (const shift of nightShifts) {
    if (shift === sourceShift) continue;
    const hasChief = schedule.records.some(
      r => leaderIds.includes(r.employeeId) && r.type === shift
    );
    if (!hasChief) targetOptions.push(shift);
  }

  // 如果没有缺主任的夜班，用白班
  if (targetOptions.length === 0) {
    targetOptions.push(ShiftType.DAY);
  }

  const changes: ConflictSuggestion['changes'] = [];

  for (let i = 0; i < excessLeaders.length && i < targetOptions.length; i++) {
    const leader = excessLeaders[i];
    const targetShift = targetOptions[i];

    // 在目标班次找一个非主任来互换（排除被用户锁定的）
    const nonLeadersOnTarget = schedule.records.filter(
      r => !leaderIds.includes(r.employeeId) && r.type === targetShift
        && !isCellLocked(lockedCells, schedule.date, r.employeeId)
    );

    if (nonLeadersOnTarget.length === 0) continue;

    const staffToSwap = nonLeadersOnTarget[0];

    changes.push(
      {
        date: schedule.date,
        employeeId: leader.employeeId,
        fromType: sourceShift,
        toType: targetShift,
        employeeName: empMap.get(leader.employeeId)?.name
      },
      {
        date: schedule.date,
        employeeId: staffToSwap.employeeId,
        fromType: targetShift,
        toType: sourceShift,
        employeeName: empMap.get(staffToSwap.employeeId)?.name
      }
    );
  }

  if (changes.length > 0) {
    return {
      description: `${getShiftName(sourceShift)}有多个主任席，建议互换调整`,
      changes
    };
  }

  return null;
}

function getShiftName(type: ShiftType): string {
  const names: Record<ShiftType, string> = {
    [ShiftType.DAY]: '白班',
    [ShiftType.SLEEP]: '睡觉班',
    [ShiftType.MINI_NIGHT]: '小夜班',
    [ShiftType.LATE_NIGHT]: '大夜班',
    [ShiftType.VACATION]: '休假',
    [ShiftType.CUSTOM]: '自定义',
    [ShiftType.NONE]: '空班',
  };
  return names[type] || type;
}
