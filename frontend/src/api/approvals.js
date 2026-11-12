import http from './index'

export const approvalsApi = {
  list: () => http.get('/approvals'),

  approve: (id) => http.post(`/approvals/${id}/approve`),

  reject: (id, reason) => http.post(`/approvals/${id}/reject`, { reason }),

  history: (id) => http.get(`/approvals/${id}/history`),
}
