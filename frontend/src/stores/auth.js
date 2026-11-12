import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api/auth'
import { useChatStore } from '@/stores/chat'
import { useOrderStore } from '@/stores/order'
import { useApprovalStore } from '@/stores/approval'
import { getToken, parseToken, removeToken, setToken as saveToken } from '@/utils/session'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(getToken())
  const userInfo = ref(null)
  const invitations = ref([])

  const isLoggedIn = computed(() => !!token.value)
  const hasTeam = computed(() => {
    if (userInfo.value?.team_id) return true
    if (!token.value) return false
    const payload = parseToken(token.value)
    return !!payload?.team_id
  })
  const teamId = computed(() => userInfo.value?.team_id ?? parseToken(token.value)?.team_id ?? null)
  const teamName = computed(() => userInfo.value?.team_name || parseToken(token.value)?.team_name || '')
  const userId = computed(() => userInfo.value?.user_id ?? parseToken(token.value)?.user_id ?? null)
  const username = computed(() => userInfo.value?.username ?? parseToken(token.value)?.username ?? '')
  const role = computed(() => userInfo.value?.role ?? parseToken(token.value)?.role ?? null)

  function setToken(newToken) {
    const oldClaims = parseToken(token.value)
    const newClaims = parseToken(newToken)
    if (oldClaims?.user_id !== newClaims?.user_id || oldClaims?.team_id !== newClaims?.team_id) {
      clearUserScopedState()
    }
    token.value = newToken
    userInfo.value = null
    invitations.value = []
    saveToken(newToken)
  }

  function logout() {
    clearUserScopedState()
    token.value = ''
    userInfo.value = null
    invitations.value = []
    removeToken()
  }

  async function login(username, password) {
    const data = await authApi.login(username, password)
    setToken(data.access_token)
    return data
  }

  async function register(username, password, accountType = 'purchaser', teamName = '') {
    const data = await authApi.register(username, password, accountType, teamName || undefined)
    setToken(data.access_token)
    return data
  }

  async function refresh() {
    if (!token.value) return null
    const claims = parseToken(token.value)
    const info = await authApi.me()
    if (claims?.user_id && String(claims.user_id) !== String(info.user_id)) {
      logout()
      throw new Error('认证身份不一致，请重新登录')
    }
    userInfo.value = info
    return userInfo.value
  }

  async function fetchInvitations() {
    invitations.value = await authApi.invitations()
    return invitations.value
  }

  async function sendInvitation(username) {
    const invitation = await authApi.sendInvitation(username)
    await fetchInvitations()
    return invitation
  }

  async function acceptInvitation(id) {
    const data = await authApi.acceptInvitation(id)
    setToken(data.access_token)
    await refresh()
    invitations.value = []
    return data
  }

  async function rejectInvitation(id) {
    await authApi.rejectInvitation(id)
    invitations.value = invitations.value.filter((item) => item.invitation_id !== id)
  }

  async function createTeam(name) {
    const data = await authApi.createTeam(name)
    // create_team 返回含 team_id 的新 token
    setToken(data.access_token)
    return data
  }

  async function joinTeam(inviteCode) {
    const data = await authApi.joinTeam(inviteCode)
    setToken(data.access_token)
    return data
  }

  async function leaveTeam() {
    const data = await authApi.leaveTeam()
    setToken(data.access_token)
    return data
  }

  function clearUserScopedState() {
    useChatStore().reset()
    useOrderStore().reset()
    useApprovalStore().clearPending()
  }

  return {
    token, userInfo, invitations,
    isLoggedIn, hasTeam, teamId, teamName, userId, username, role,
    setToken, logout, login, register, refresh, fetchInvitations,
    sendInvitation, acceptInvitation, rejectInvitation, createTeam, joinTeam, leaveTeam,
  }
})
