import http from './index'

export const authApi = {
  login: (username, password) =>
    http.post('/auth/login', { username, password }),

  register: (username, password, account_type, team_name) =>
    http.post('/auth/register', { username, password, account_type, team_name }),

  me: () => http.get('/auth/me'),

  createTeam: (name) => http.post('/auth/team', { name }),

  joinTeam: (invite_code) => http.post('/auth/team/join', { invite_code }),

  leaveTeam: () => http.post('/auth/team/leave'),

  invitations: () => http.get('/auth/team/invitations'),

  sendInvitation: (username) => http.post('/auth/team/invitations', { username }),

  acceptInvitation: (id) => http.post(`/auth/team/invitations/${id}/accept`),

  rejectInvitation: (id) => http.post(`/auth/team/invitations/${id}/reject`),
}
