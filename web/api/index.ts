/**
 * API 服务层
 * 封装所有后端 API 调用
 */
import { get, post, put, del } from '../utils/request';
import request from '../utils/request';

// ============================================
// 类型定义（与后端 DTO 对应）
// ============================================

export interface EmployeeDTO {
  id: number;
  name: string;
  is_night_leader: boolean;
  sequence_order: number;
  avoidance_group_id: number | null;
}

export interface AvoidanceRuleDTO {
  id: number;
  name: string | null;
  member_ids: number[];
  description: string | null;
}

export interface ShiftRecordDTO {
  employee_id: number;
  date: string;
  shift_type: string;
  seat_type: string | null;
}

export interface DailyScheduleDTO {
  date: string;
  day_of_week: string;
  records: ShiftRecordDTO[];
}

export interface InitDataResponse {
  month: string;
  group_id: string;
  work_days: string[];
  employees: EmployeeDTO[];
  schedules: DailyScheduleDTO[];
  avoidance_rules: AvoidanceRuleDTO[];
  anchor_date: string;
  anchor_group: string;
}

export interface AutoGenerateRequest {
  month: string;
  group_id: string;
  start_date?: string;
  end_date?: string;
}

export interface AutoGenerateResponse {
  month: string;
  group_id: string;
  work_days: string[];
  schedules: DailyScheduleDTO[];
  statistics: Record<string, any>;
}

export interface SaveScheduleRequest {
  month: string;
  group_id: string;
  schedules: DailyScheduleDTO[];
}

export interface SaveScheduleResponse {
  success: boolean;
  message: string;
  saved_count: number;
}

export interface UpdateShiftRequest {
  employee_id: number;
  date: string;
  shift_type: string;
  group_id: string;
  seat_type?: string | null;
  label?: string | null;
}

export interface UpdateShiftResponse {
  success: boolean;
  message: string;
}

export interface EmployeeCreateRequest {
  name: string;
  is_night_leader?: boolean;
  sequence_order?: number;
  avoidance_group_id?: number | null;
}

export interface EmployeeUpdateRequest {
  name?: string;
  is_night_leader?: boolean;
  sequence_order?: number;
  avoidance_group_id?: number | null;
}

export interface SetFirstWorkDayRequest {
  month: string;
  group_id: string;
  first_work_day: number;
}

export interface SetFirstWorkDayResponse {
  success: boolean;
  message: string;
  work_days: string[];
  config_key: string;
}

// ============================================
// API 函数
// ============================================

/**
 * 获取初始化数据
 * @param month 月份，格式 YYYY-MM
 * @param groupId 组别 A/B/C
 */
export const fetchInitData = async (month: string, groupId: string): Promise<InitDataResponse> => {
  return get<InitDataResponse>('/api/init-data', { month, group_id: groupId });
};

/**
 * 自动生成排班（预览，不存库）
 */
export const autoGenerateSchedule = async (params: AutoGenerateRequest): Promise<AutoGenerateResponse> => {
  return post<AutoGenerateResponse>('/api/schedule/auto-generate', params);
};

/**
 * 保存排班数据
 */
export const saveSchedule = async (params: SaveScheduleRequest): Promise<SaveScheduleResponse> => {
  return post<SaveScheduleResponse>('/api/schedule/save', params);
};

/**
 * 更新单个班次（实时保存）
 */
export const updateShift = async (params: UpdateShiftRequest): Promise<UpdateShiftResponse> => {
  return put<UpdateShiftResponse>('/api/schedule/shift', params);
};

/**
 * 导出 Excel 文件
 * @param month 月份
 * @param groupId 组别
 */
export const exportSchedule = async (month: string, groupId: string): Promise<Blob> => {
  const response = await request.get('/api/export', {
    params: { month, group_id: groupId },
    responseType: 'blob',
  });
  return response.data;
};

/**
 * 下载 Excel 文件
 */
export const downloadExcel = async (month: string, groupId: string): Promise<void> => {
  const blob = await exportSchedule(month, groupId);
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `schedule_${month}_${groupId}.xlsx`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};

/**
 * 获取工作日列表
 */
export const fetchWorkDays = async (month: string, groupId: string): Promise<{ work_days: string[]; count: number }> => {
  return get(`/api/schedule/workdays/${month}/${groupId}`);
};

/**
 * 设置首个工作日
 */
export const setFirstWorkDay = async (params: SetFirstWorkDayRequest): Promise<SetFirstWorkDayResponse> => {
  return post<SetFirstWorkDayResponse>('/api/workday/set-first-day', params);
};

// ============================================
// 员工管理 API
// ============================================

/**
 * 获取所有员工
 */
export const fetchEmployees = async (): Promise<EmployeeDTO[]> => {
  return get<EmployeeDTO[]>('/api/employees');
};

/**
 * 创建新员工
 */
export const createEmployee = async (data: EmployeeCreateRequest): Promise<EmployeeDTO> => {
  return post<EmployeeDTO>('/api/employees', data);
};

/**
 * 更新员工信息
 */
export const updateEmployee = async (id: number, data: EmployeeUpdateRequest): Promise<EmployeeDTO> => {
  return put<EmployeeDTO>(`/api/employees/${id}`, data);
};

/**
 * 删除员工
 */
export const deleteEmployee = async (id: number): Promise<{ success: boolean; message: string }> => {
  return del(`/api/employees/${id}`);
};

// ============================================
// 健康检查
// ============================================

/**
 * 检查后端服务状态
 */
export const checkHealth = async (): Promise<{ status: string; db_available: boolean }> => {
  return get('/health');
};
