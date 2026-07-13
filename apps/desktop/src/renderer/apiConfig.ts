/**
 * 前端 API 配置
 *
 * 通过环境变量 OFFICEAGENT_BACKEND_URL 或默认值设置后端地址。
 * 所有渲染进程文件通过此文件统一引用 API 地址。
 */

/** 后端 API 基础地址 */
export const API_BASE =
  (typeof process !== 'undefined' && process.env?.OFFICEAGENT_BACKEND_URL) ||
  'http://localhost:8765';

export default API_BASE;