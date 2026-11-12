import http from './index'

export const ordersApi = {
  list: (params) => http.get('/orders', { params }),

  create: (project_id, name, remark) => http.post('/orders', { project_id, name, remark }),

  update: (id, data) => http.put(`/orders/${id}`, data),

  get: (id) => http.get(`/orders/${id}`),

  supplierOptions: (id) => http.get(`/orders/${id}/supplier-options`),

  supplierOrders: (params = {}) => http.get('/orders/supplier-orders', { params }),

  removeSupplierOrder: (id) => http.delete(`/orders/supplier-orders/${id}`),

  supplierOrderDownload: (id, fileFormat, itemId) => http.get(
    `/orders/supplier-orders/${id}/download`,
    { params: { file_format: fileFormat, item_id: itemId }, responseType: 'blob' },
  ),

  remove: (id) => http.delete(`/orders/${id}`),

  saveItems: (id, items) => http.put(`/orders/${id}/items`, items),

  submit: (id) => http.post(`/orders/${id}/submit`),

  receive: (id) => http.post(`/orders/${id}/receive`),

  inquiryTemplates: () => http.get('/orders/inquiry/templates'),

  generateInquiry: (id, template_id) =>
    http.post(`/orders/${id}/inquiry`, { order_id: id, template_id }),

  downloadInquiry: (id) =>
    http.get(`/orders/${id}/inquiry/download`, { responseType: 'blob' }),

  compare: (id, quotes) =>
    http.post(`/orders/${id}/compare`, { order_id: id, quotes }),
}
