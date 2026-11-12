import http from './index'

export const projectsApi = {
  list: () => http.get('/projects'),

  create: (name, remark) => http.post('/projects', { name, remark }),

  get: (id) => http.get(`/projects/${id}`),

  update: (id, data) => http.patch(`/projects/${id}`, data),

  remove: (id) => http.delete(`/projects/${id}`),
}
