
const API_BASE_URL = 'http://101.37.203.158:8000';

// ==================== 后端 DTO 类型定义 ====================

export interface EmployeeDTO {
  id: number;
  name: string;
  is_night_leader: boolean;
  sequence_order: number;
  avoidance_group_id: number | null;
}

export interface ShiftRecordDTO {
  employee_id: number;
  date: string;
  shift_type: string;
  seat_type: string | null;
  label: string | null;
}

export interface DailyScheduleDTO {
  date: string;
  day_of_week: string;
  records: ShiftRecordDTO[];
}

export interface AvoidanceRuleDTO {
  id: number;
  name: string | null;
  member_ids: number[];
  description: string | null;
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
  locked_records?: Array<{
    employee_id: number;
    date: string;
    shift_type: string;
  }>; // 新增：锁定的单元格
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
  group_id: string; // 新增：必填
  is_night_leader: boolean;
  sequence_order?: number;
  avoidance_group_id?: number;
}

export interface EmployeeUpdateRequest {
  name?: string;
  group_id?: string; // 新增：可选
  is_night_leader?: boolean;
  sequence_order?: number;
  avoidance_group_id?: number;
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

// ==================== API 函数 ====================

/**
 * 检查后端服务健康状态
 */
export async function checkHealth(): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE_URL}/health`);
  if (!response.ok) throw new Error('Health check failed');
  return response.json();
}

/**
 * 获取初始化数据
 */
export async function fetchInitData(month: string, groupId: string): Promise<InitDataResponse> {
  const response = await fetch(`${API_BASE_URL}/api/init-data?month=${month}&group_id=${groupId}`);
  if (!response.ok) throw new Error(`Failed to fetch init data: ${response.statusText}`);
  return response.json();
}

/**
 * 自动生成排班
 */
export async function autoGenerateSchedule(request: AutoGenerateRequest): Promise<AutoGenerateResponse> {
  const response = await fetch(`${API_BASE_URL}/api/schedule/auto-generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!response.ok) throw new Error(`Auto generate failed: ${response.statusText}`);
  return response.json();
}

/**
 * 保存排班数据
 */
export async function saveSchedule(request: SaveScheduleRequest): Promise<SaveScheduleResponse> {
  const response = await fetch(`${API_BASE_URL}/api/schedule/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!response.ok) throw new Error(`Save failed: ${response.statusText}`);
  return response.json();
}

/**
 * 更新单个班次（实时保存）
 */
export async function updateShift(request: UpdateShiftRequest): Promise<UpdateShiftResponse> {
  const response = await fetch(`${API_BASE_URL}/api/schedule/shift`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!response.ok) throw new Error(`Update shift failed: ${response.statusText}`);
  return response.json();
}

/**
 * 导出 Excel
 */
export async function downloadExcel(month: string, groupId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/export?month=${month}&group_id=${groupId}`);
  if (!response.ok) throw new Error(`Export failed: ${response.statusText}`);

  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `schedule_${month}_${groupId}.xlsx`;
  document.body.appendChild(a);
  a.click();
  window.URL.revokeObjectURL(url);
  document.body.removeChild(a);
}

/**
 * 获取所有员工
 */
export async function fetchEmployees(): Promise<EmployeeDTO[]> {
  const response = await fetch(`${API_BASE_URL}/api/employees`);
  if (!response.ok) throw new Error(`Failed to fetch employees: ${response.statusText}`);
  return response.json();
}

/**
 * 创建员工
 */
export async function createEmployee(request: EmployeeCreateRequest): Promise<EmployeeDTO> {
  const response = await fetch(`${API_BASE_URL}/api/employees`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!response.ok) throw new Error(`Create employee failed: ${response.statusText}`);
  return response.json();
}

/**
 * 更新员工
 */
export async function updateEmployee(id: number, request: EmployeeUpdateRequest): Promise<EmployeeDTO> {
  const response = await fetch(`${API_BASE_URL}/api/employees/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!response.ok) throw new Error(`Update employee failed: ${response.statusText}`);
  return response.json();
}

/**
 * 删除员工
 */
export async function deleteEmployee(id: number): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/employees/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error(`Delete employee failed: ${response.statusText}`);
}

/**
 * 设置首个工作日
 */
export async function setFirstWorkDay(request: SetFirstWorkDayRequest): Promise<SetFirstWorkDayResponse> {
  const response = await fetch(`${API_BASE_URL}/api/workday/set-first-day`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!response.ok) throw new Error(`Set first work day failed: ${response.statusText}`);
  return response.json();
}

/**
 * 验证单日排班
 */
export async function validateDaySchedule(date: string, records: ShiftRecordDTO[]): Promise<{
  is_valid: boolean;
  errors: Array<{
    type: string;
    date: string;
    message: string;
    employee_ids: number[];
  }>;
}> {
  const response = await fetch(`${API_BASE_URL}/api/schedule/validate-day?date=${date}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(records),
  });
  if (!response.ok) throw new Error(`Validation failed: ${response.statusText}`);
  return response.json();
}

/**
 * 验证整月排班
 */
export async function validateMonthSchedule(schedules: DailyScheduleDTO[]): Promise<{
  is_valid: boolean;
  errors: Array<{
    type: string;
    date: string;
    message: string;
    employee_ids: number[];
  }>;
  summary: {
    total_errors: number;
    error_types: string[];
  };
}> {
  const response = await fetch(`${API_BASE_URL}/api/schedule/validate-month`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(schedules),
  });
  if (!response.ok) throw new Error(`Validation failed: ${response.statusText}`);
  return response.json();
}
