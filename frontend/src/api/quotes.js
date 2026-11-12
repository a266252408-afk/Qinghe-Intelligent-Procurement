import http from './index'

export const quotesApi = {
  parse: (orderId, file) => {
    const formData = new FormData()
    if (orderId) formData.append('order_id', orderId)
    formData.append('file', file)
    return http.post('/quotes/parse', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  create: (data) => http.post('/quotes', data),
  list: (params = {}) => http.get('/quotes', { params }),

  remove: (id) => http.delete(`/quotes/${id}`),
}
