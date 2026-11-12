import http from './index'
import { getToken } from '@/utils/session'

export const knowledgeApi = {
  search: (q) => http.get('/knowledge/search', { params: { q } }),
  history: (params = {}) => http.get('/knowledge/history', { params }),

  uploadIndustry: (formData, onUploadProgress) => uploadIndustryFile(formData, onUploadProgress),
  listIndustryDocs: () => http.get('/knowledge/industry/documents'),

  extract: (text) => http.post('/knowledge/extract', null, { params: { text } }),

  save: (data) => http.post('/knowledge/save', data),

  createSession: (project_id, title) =>
    http.post('/knowledge/sessions', { project_id, title }),

  getMessages: (session_id) =>
    http.get(`/knowledge/sessions/${session_id}/messages`),

  listSessions: (project_id) =>
    http.get('/knowledge/sessions', { params: { project_id } }),

  deleteSession: (session_id) =>
    http.delete(`/knowledge/sessions/${session_id}`),
}

function uploadIndustryFile(formData, onUploadProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/knowledge/industry/upload')
    xhr.timeout = 300000
    const token = getToken()
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)

    xhr.upload.onprogress = (event) => {
      onUploadProgress?.(event)
    }
    xhr.upload.onload = () => {
      const total = xhr.upload.total || 1
      onUploadProgress?.({ loaded: total, total })
    }
    xhr.onload = () => {
      const body = parseResponse(xhr.responseText)
      if (xhr.status >= 200 && xhr.status < 300 && body?.code === 0) {
        resolve(body.data)
        return
      }
      reject(createUploadError(xhr.status, body))
    }
    xhr.onerror = () => reject(new Error('网络连接失败，请检查后端服务。'))
    xhr.ontimeout = () => reject(new Error('文档处理超时，请稍后重试。'))
    xhr.send(formData)
  })
}

function parseResponse(text) {
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

function createUploadError(status, body) {
  const error = new Error(body?.msg || body?.detail || `上传失败（${status}）`)
  error.response = { status, data: body }
  return error
}
