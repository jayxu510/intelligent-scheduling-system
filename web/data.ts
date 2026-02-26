
import { Employee, EmployeeRole, ShiftType, DailySchedule, ShiftRecord } from './types';

// 静态员工数据已移除，现从数据库动态加载
// 员工数据通过 API GET /api/init-data 或 /api/employees 获取

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];

export const generateMonthSchedules = (year: number, month: number, employees: Employee[]): DailySchedule[] => {
  const schedules: DailySchedule[] = [];
  const daysInMonth = new Date(year, month + 1, 0).getDate();

  for (let day = 1; day <= daysInMonth; day++) {
    const dateStr = `${year}-${(month + 1).toString().padStart(2, '0')}-${day.toString().padStart(2, '0')}`;
    const dateObj = new Date(year, month, day);
    const dayOfWeek = WEEKDAYS[dateObj.getDay()];

    schedules.push({
      date: dateStr,
      dayOfWeek,
      records: employees.map((emp) => ({
        employeeId: emp.id,
        date: dateStr,
        type: ShiftType.NONE, // Matches requirement: "Every month initial shifts are empty"
      }))
    });
  }
  return schedules;
};

/**
 * 单日排班算法（本地回退/单日刷新用）
 *
 * 保证满足所有硬约束：
 * - DAY=6, SLEEP=5, MINI_NIGHT=3, LATE_NIGHT=3（共17人）
 * - 每个夜班类型恰好1名主任资质人员（前6人）
 * - 不会出现主任席缺失或重复的冲突
 */
export const autoScheduleRowLogic = (date: string, employees: Employee[]): ShiftRecord[] => {
  // 需要恰好17人才能满足岗位定员
  if (employees.length < 17) {
    return employees.map(emp => ({
      employeeId: emp.id,
      date,
      type: ShiftType.NONE,
    }));
  }

  // 前6人为主任资质（leaders），其余为普通员工（staff）
  const leaders = employees.slice(0, 6);
  const staff = employees.slice(6, 17);
  const extra = employees.slice(17); // 超出17人的部分

  // Fisher-Yates 洗牌
  const shuffle = <T,>(arr: T[]): T[] => {
    const a = [...arr];
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  };

  const shuffledLeaders = shuffle(leaders);
  const shuffledStaff = shuffle(staff);

  const assignments = new Map<string, ShiftType>();

  // 规则：第一列人员按"1个白班 + 2个睡觉班"循环（用日期号 mod 3 判断）
  const firstEmpId = employees[0].id;
  const dayNum = parseInt(date.split('-')[2]);
  const firstEmpShift = (dayNum % 3 === 1) ? ShiftType.DAY : ShiftType.SLEEP;

  // 主任分配：1人SLEEP + 1人MINI_NIGHT + 1人LATE_NIGHT + 3人DAY = 6
  // 根据第一人应该的班次来决定分配
  const firstIsLeader = shuffledLeaders.some(l => l.id === firstEmpId);

  if (firstIsLeader && firstEmpShift === ShiftType.SLEEP) {
    // 第一人是主任且应该上睡觉班，让他当睡觉班主任
    assignments.set(firstEmpId, ShiftType.SLEEP);
    const otherLeaders = shuffledLeaders.filter(l => l.id !== firstEmpId);
    assignments.set(otherLeaders[0].id, ShiftType.MINI_NIGHT);
    assignments.set(otherLeaders[1].id, ShiftType.LATE_NIGHT);
    for (let i = 2; i < otherLeaders.length; i++) {
      assignments.set(otherLeaders[i].id, ShiftType.DAY);
    }
  } else if (firstIsLeader && firstEmpShift === ShiftType.DAY) {
    // 第一人是主任且应该上白班
    assignments.set(firstEmpId, ShiftType.DAY);
    const otherLeaders = shuffledLeaders.filter(l => l.id !== firstEmpId);
    assignments.set(otherLeaders[0].id, ShiftType.SLEEP);
    assignments.set(otherLeaders[1].id, ShiftType.MINI_NIGHT);
    assignments.set(otherLeaders[2].id, ShiftType.LATE_NIGHT);
    for (let i = 3; i < otherLeaders.length; i++) {
      assignments.set(otherLeaders[i].id, ShiftType.DAY);
    }
  } else {
    // 第一人不是主任，正常分配主任
    assignments.set(shuffledLeaders[0].id, ShiftType.SLEEP);
    assignments.set(shuffledLeaders[1].id, ShiftType.MINI_NIGHT);
    assignments.set(shuffledLeaders[2].id, ShiftType.LATE_NIGHT);
    for (let i = 3; i < 6; i++) {
      assignments.set(shuffledLeaders[i].id, ShiftType.DAY);
    }
  }

  // 普通员工分配：根据已分配主任的情况，填满定员
  // 定员：DAY=6, SLEEP=5, MINI_NIGHT=3, LATE_NIGHT=3
  const currentCounts = {
    [ShiftType.DAY]: 0,
    [ShiftType.SLEEP]: 0,
    [ShiftType.MINI_NIGHT]: 0,
    [ShiftType.LATE_NIGHT]: 0,
  };

  // 统计已分配的主任各班次人数
  for (const [empId, shift] of assignments.entries()) {
    if (shift in currentCounts) {
      currentCounts[shift as keyof typeof currentCounts]++;
    }
  }

  const needed = {
    [ShiftType.SLEEP]: 5 - currentCounts[ShiftType.SLEEP],
    [ShiftType.MINI_NIGHT]: 3 - currentCounts[ShiftType.MINI_NIGHT],
    [ShiftType.LATE_NIGHT]: 3 - currentCounts[ShiftType.LATE_NIGHT],
    [ShiftType.DAY]: 6 - currentCounts[ShiftType.DAY],
  };

  // 如果第一人不是主任且还没分配，优先分配
  if (!firstIsLeader && !assignments.has(firstEmpId)) {
    assignments.set(firstEmpId, firstEmpShift);
    if (firstEmpShift in needed) {
      needed[firstEmpShift as keyof typeof needed]--;
    }
  }

  // 分配剩余普通员工
  const availableStaff = shuffledStaff.filter(s => !assignments.has(s.id));
  let idx = 0;

  for (let i = 0; i < needed[ShiftType.SLEEP] && idx < availableStaff.length; i++) {
    assignments.set(availableStaff[idx++].id, ShiftType.SLEEP);
  }
  for (let i = 0; i < needed[ShiftType.MINI_NIGHT] && idx < availableStaff.length; i++) {
    assignments.set(availableStaff[idx++].id, ShiftType.MINI_NIGHT);
  }
  for (let i = 0; i < needed[ShiftType.LATE_NIGHT] && idx < availableStaff.length; i++) {
    assignments.set(availableStaff[idx++].id, ShiftType.LATE_NIGHT);
  }
  for (let i = 0; i < needed[ShiftType.DAY] && idx < availableStaff.length; i++) {
    assignments.set(availableStaff[idx++].id, ShiftType.DAY);
  }

  // 超出的员工设为NONE
  for (const emp of extra) {
    assignments.set(emp.id, ShiftType.NONE);
  }

  return employees.map(emp => ({
    employeeId: emp.id,
    date,
    type: assignments.get(emp.id) || ShiftType.NONE,
  }));
};
