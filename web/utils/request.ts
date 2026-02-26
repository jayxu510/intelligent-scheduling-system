/**
 * Axios 请求封装
 * 统一处理 BaseURL 和错误拦截
 */
import axios, { AxiosInstance, AxiosError, AxiosResponse } from 'axios';

// API 基础URL - 从环境变量读取或使用默认值
const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// 创建 Axios 实例
const request: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 60000, // 60秒超时（排班算法可能需要较长时间）
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器
request.interceptors.request.use(
  (config) => {
    // 可以在这里添加 token 等认证信息
    // const token = localStorage.getItem('token');
    // if (token) {
    //   config.headers.Authorization = `Bearer ${token}`;
    // }
    console.log(`[API Request] ${config.method?.toUpperCase()} ${config.url}`);
    return config;
  },
  (error: AxiosError) => {
    console.error('[API Request Error]', error);
    return Promise.reject(error);
  }
);

// 响应拦截器
request.interceptors.response.use(
  (response: AxiosResponse) => {
    console.log(`[API Response] ${response.config.url}`, response.status);
    return response;
  },
  (error: AxiosError) => {
    // 统一错误处理
    if (error.response) {
      const { status, data } = error.response;

      switch (status) {
        case 400:
          console.error('[API Error 400] Bad Request:', data);
          break;
        case 401:
          console.error('[API Error 401] Unauthorized');
          // 可以在这里处理登录过期
          break;
        case 403:
          console.error('[API Error 403] Forbidden');
          break;
        case 404:
          console.error('[API Error 404] Not Found:', error.config?.url);
          break;
        case 500:
          console.error('[API Error 500] Server Error:', data);
          break;
        default:
          console.error(`[API Error ${status}]`, data);
      }
    } else if (error.request) {
      // 请求已发送但没有收到响应
      console.error('[API Error] No response received:', error.message);
    } else {
      // 请求配置出错
      console.error('[API Error] Request setup failed:', error.message);
    }

    return Promise.reject(error);
  }
);

export default request;

// 导出便捷方法
export const get = <T = any>(url: string, params?: any) =>
  request.get<T>(url, { params }).then(res => res.data);

export const post = <T = any>(url: string, data?: any) =>
  request.post<T>(url, data).then(res => res.data);

export const put = <T = any>(url: string, data?: any) =>
  request.put<T>(url, data).then(res => res.data);

export const del = <T = any>(url: string) =>
  request.delete<T>(url).then(res => res.data);
