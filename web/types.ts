
export enum ShiftType {
  DAY = 'DAY',
  SLEEP = 'SLEEP',
  MINI_NIGHT = 'MINI_NIGHT',
  LATE_NIGHT = 'LATE_NIGHT',
  VACATION = 'VACATION',
  CUSTOM = 'CUSTOM',
  NONE = 'NONE',
}

export enum EmployeeRole {
  LEADER = 'LEADER',
  STAFF = 'STAFF',
}

export interface Employee {
  id: string;
  name: string;
  role: EmployeeRole;
  title?: string;
  avoidanceGroupId?: string;
  sequenceOrder?: number;
}

export interface ShiftRecord {
  employeeId: string;
  date: string;
  type: ShiftType;
  label?: string;
  seatType?: string;
  isLocked?: boolean; // 新增：是否锁定
}

export interface ConflictSuggestion {
  description: string;
  changes: Array<{
    date: string;
    employeeId: string;
    fromType: ShiftType;
    toType: ShiftType;
    employeeName?: string;
  }>;
}

export interface Conflict {
  type: 'AVOIDANCE' | 'AVOIDANCE_CONFLICT' | 'REST' | 'ROLE_MISMATCH' | 'CHIEF_MISSING' | 'CHIEF_DUPLICATE' | 'SLOT_COUNT_MISMATCH' | 'TOTAL_COUNT_MISMATCH' | 'CONSECUTIVE_VIOLATION';
  employeeIds: string[];
  date: string;
  shiftType?: ShiftType;
  message: string;
  suggestion?: ConflictSuggestion;
}

export interface DailySchedule {
  date: string;
  dayOfWeek: string;
  records: ShiftRecord[];
}

// 避让规则
export interface AvoidanceRule {
  id: string;
  name?: string;
  memberIds: string[];
  description?: string;
}

// 应用状态
export interface AppState {
  employees: Employee[];
  schedules: DailySchedule[];
  avoidanceRules: AvoidanceRule[];
  workDays: string[];
  anchorDate: string;
  anchorGroup: string;
  isLoading: boolean;
  error: string | null;
}
