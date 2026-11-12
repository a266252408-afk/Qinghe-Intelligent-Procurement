import http from './index'

export const receiptsApi = {
  list: () => http.get('/receipts'),
  get: (id) => http.get(`/receipts/${id}`),
  remove: (id) => http.delete(`/receipts/${id}`),
  update: (id, data) => http.patch(`/receipts/${id}`, data),
  confirm: (id) => http.post(`/receipts/${id}/confirm`),
}
