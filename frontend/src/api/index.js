import axios from 'axios'
import { ElMessage } from 'element-plus'
import { getToken, removeToken } from '@/utils/session'

const http = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 请求拦截：注入 Bearer token
http.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 响应拦截：统一错误处理
http.interceptors.response.use(
  (res) => {
    // 文件下载不经过统一 JSON 响应格式处理，直接返回 Blob
    if (res.config.responseType === 'blob') return res.data
    const data = res.data
    if (data.code !== 0) {
      ElMessage.error(data.msg || '请求失败')
      return Promise.reject(new Error(data.msg))
    }
    return data.data
  },
  (err) => {
    if (err.response?.status === 401) {
      removeToken()
      window.location.href = '/login'
    } else {
      const body = err.response?.data
      ElMessage.error(body?.msg || body?.detail || err.message || '网络错误')
    }
    return Promise.reject(err)
  },
)

export default http
