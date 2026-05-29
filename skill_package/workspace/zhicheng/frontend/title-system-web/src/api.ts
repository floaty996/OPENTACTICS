const API_BASE = '/api';

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(err.detail || '请求失败');
  }
  return res.json();
}

export interface Employee {
  emp_id: string;
  name: string;
  department: string;
  job_position: string;
  education: string;
  professional_title: string;
  seniority: number;
  hire_date: string;
  [key: string]: unknown;
}

export interface Application {
  id: number;
  emp_id: string;
  emp_name: string;
  department: string;
  current_title: string;
  applied_title: string;
  education: string;
  job_position: string;
  seniority: number;
  reason?: string;
  status: string;
  reviewer?: string;
  review_comment?: string;
  review_time?: string;
  created_at?: string;
  updated_at?: string;
}

export interface PaginatedRes<T> {
  total: number;
  page: number;
  page_size: number;
  data: T[];
}

export interface OverviewData {
  employee_count: number;
  department_count: number;
  title_distribution: Record<string, number>;
  application_count: number;
  application_status: Record<string, number>;
}

export interface DeptDistRow {
  department: string;
  no_title: number;
  junior: number;
  mid: number;
  senior: number;
  total: number;
}

export interface EduDistRow {
  education: string;
  no_title: number;
  junior: number;
  mid: number;
  senior: number;
  total: number;
}

/** 获取员工列表（普通查询） */
export function fetchEmployees(params: { keyword?: string; department?: string; page?: number; page_size?: number }) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== '') q.set(k, String(v)); });
  return request<PaginatedRes<Employee>>(`/employees?${q}`);
}

/** 按职称筛选员工（走独立路由避免与 /employees/{emp_id} 冲突） */
export function fetchEmployeesByTitle(params: { professional_title: string; department?: string; page?: number; page_size?: number }) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== '') q.set(k, String(v)); });
  return request<PaginatedRes<Employee> & { title: string }>(`/employees-by-title?${q}`);
}

/** 获取单个员工 */
export function fetchEmployee(empId: string) {
  return request<Employee>(`/employees/${empId}`);
}

/** 部门列表 */
export function fetchDepartments() {
  return request<{ data: string[] }>('/employees/departments');
}

/** 获取申请列表 */
export function fetchApplications(params: { status?: string; emp_id?: string; department?: string; page?: number; page_size?: number }) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== '') q.set(k, String(v)); });
  return request<PaginatedRes<Application>>(`/applications?${q}`);
}

/** 获取单个申请 */
export function fetchApplication(id: number) {
  return request<Application>(`/applications/${id}`);
}

/** 提交申请 */
export function createApplication(body: { emp_id: string; applied_title: string; reason?: string }) {
  return request<{ ok: boolean; message: string; id: number }>('/applications', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/** 审批申请 */
export function reviewApplication(id: number, body: { reviewer: string; review_comment?: string; action: 'approve' | 'reject' }) {
  return request<{ ok: boolean; message: string }>(`/applications/${id}/review`, {
    method: 'PUT',
    body: JSON.stringify(body),
  });
}

/** 概览数据 */
export function fetchOverview() {
  return request<OverviewData>('/statistics/overview');
}

/** 部门职称分布 */
export function fetchTitleDistribution(department?: string) {
  const q = department ? `?department=${encodeURIComponent(department)}` : '';
  return request<{ data: DeptDistRow[] }>(`/statistics/title-distribution${q}`);
}

/** 学历职称分布 */
export function fetchTitleByEducation() {
  return request<{ data: EduDistRow[] }>('/statistics/title-by-education');
}
