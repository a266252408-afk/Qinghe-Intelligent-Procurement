import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import { knowledgeApi } from '@/api/knowledge'
import { streamChat } from '@/api/chat'
import { getToken, parseToken } from '@/utils/session'

export const useChatStore = defineStore('chat', () => {
  const sessions = ref([])          // { session_id, title, project_id }
  const currentSessionId = ref(null)
  const messages = ref([])          // { role, content, type?, data? }
  const isStreaming = ref(false)
  const structuredResult = ref(null) // 最新结构化结果（表格/图表数据）
  const pendingRouteConfirm = ref(null) // 低置信度路由待人工确认的 payload

  function storageKey(name) {
    const token = getToken()
    let userKey = 'anonymous'
    userKey = parseToken(token)?.user_id || userKey
    return `chat:${userKey}:${name}`
  }

  function resultKey(result) {
    return result ? JSON.stringify({ type: result.type, data: result.data }) : ''
  }

  function saveSelection(projectId, sessionId = null) {
    if (projectId) sessionStorage.setItem(storageKey('project'), String(projectId))
    if (sessionId !== null) {
      if (sessionId) sessionStorage.setItem(storageKey('session'), String(sessionId))
      else sessionStorage.removeItem(storageKey('session'))
    }
  }

  function clearSelection() {
    sessionStorage.removeItem(storageKey('project'))
    sessionStorage.removeItem(storageKey('session'))
  }

  async function createSession(projectId, title) {
    const data = await knowledgeApi.createSession(projectId, title || '新对话')
    sessions.value.unshift(data)
    currentSessionId.value = data.session_id
    messages.value = []
    pendingRouteConfirm.value = null
    saveSelection(projectId, data.session_id)
    return data
  }

  function isRouteConfirmExpired(data) {
    if (!data?.created_at || !data?.ttl_minutes) return false
    const created = new Date(data.created_at).getTime()
    if (Number.isNaN(created)) return false
    return Date.now() > created + Number(data.ttl_minutes) * 60 * 1000
  }

  async function loadMessages(sessionId) {
    currentSessionId.value = sessionId
    const msgs = await knowledgeApi.getMessages(sessionId)
    messages.value = msgs
    // route_confirm 是弹窗状态，不是结果抽屉内容，必须排除
    const structured = [...msgs].reverse().find(
      (item) => item.metadata?.structured_type
        && item.metadata.structured_type !== 'route_confirm'
    )
    const restored = structured
      ? { type: structured.metadata.structured_type, data: structured.metadata.structured_data }
      : null
    const dismissed = sessionStorage.getItem(storageKey('dismissed-result'))
    structuredResult.value = restored && resultKey(restored) !== dismissed ? restored : null

    const pendingConfirm = [...msgs].reverse().find((item) => {
      const meta = item.metadata || {}
      return meta.structured_type === 'route_confirm'
        && meta.structured_data?.status === 'pending'
    })
    const confirmData = pendingConfirm?.metadata?.structured_data || null
    pendingRouteConfirm.value = confirmData && !isRouteConfirmExpired(confirmData)
      ? confirmData
      : null

    const session = sessions.value.find((item) => item.session_id === sessionId)
    saveSelection(session?.project_id, sessionId)
  }

  async function loadSessions(projectId, preferredSessionId = null) {
    const list = await knowledgeApi.listSessions(projectId)
    sessions.value = list
    const savedSessionId = preferredSessionId || sessionStorage.getItem(storageKey('session'))
    const selected = list.find((item) => String(item.session_id) === String(savedSessionId))
    currentSessionId.value = selected?.session_id || null
    messages.value = []
    structuredResult.value = null
    pendingRouteConfirm.value = null
    saveSelection(projectId, selected?.session_id || '')
    if (selected) {
      await loadMessages(selected.session_id)
    }
    return list
  }

  async function deleteSession(sessionId) {
    await knowledgeApi.deleteSession(sessionId)
    sessions.value = sessions.value.filter((item) => item.session_id !== sessionId)
    if (currentSessionId.value === sessionId) {
      const next = sessions.value[0]
      currentSessionId.value = next?.session_id || null
      messages.value = []
      pendingRouteConfirm.value = null
      if (next) await loadMessages(next.session_id)
      else sessionStorage.removeItem(storageKey('session'))
    }
  }

  function resetConversation() {
    sessions.value = []
    currentSessionId.value = null
    messages.value = []
    structuredResult.value = null
    pendingRouteConfirm.value = null
  }

  function applyChunk(chunk, assistantMsg, resolve) {
    if (chunk.delta) {
      assistantMsg.content += chunk.delta
    }
    if (chunk.type === 'route_confirm' && chunk.data) {
      // 待确认路由走独立弹窗，不能写 structuredResult（否则会误开结果抽屉）
      pendingRouteConfirm.value = chunk.data
    } else if (chunk.type && chunk.data) {
      structuredResult.value = { type: chunk.type, data: chunk.data }
    }
    if (chunk.done) {
      assistantMsg.streaming = false
      isStreaming.value = false
      resolve()
    }
  }

  async function sendMessage(content, fileInfo = null) {
    // 待确认期间禁止插入新消息，必须先完成人工选择
    if (pendingRouteConfirm.value) return

    // 追加用户消息到界面
    messages.value.push({
      role: 'user',
      content,
      metadata: fileInfo
        ? { file_name: fileInfo.file_name, file_type: fileInfo.file_type }
        : null,
    })

    // 追加 assistant 占位消息（流式追加），用 reactive 确保 Vue 追踪属性变化
    const assistantMsg = reactive({ role: 'assistant', content: '', streaming: true })
    messages.value.push(assistantMsg)
    isStreaming.value = true

    const payload = {
      session_id: currentSessionId.value ? String(currentSessionId.value) : '',
      message: content,
      ...(fileInfo ? { file_id: fileInfo.file_id, file_type: fileInfo.file_type } : {}),
      ...(fileInfo?.file_name ? { file_name: fileInfo.file_name } : {}),
      ...(fileInfo?.upload_id ? { upload_id: fileInfo.upload_id } : {}),
    }

    await new Promise((resolve) => {
      streamChat(
        payload,
        (chunk) => applyChunk(chunk, assistantMsg, resolve),
        (err) => {
          assistantMsg.content += '\n\n[连接中断]'
          assistantMsg.streaming = false
          isStreaming.value = false
          console.error('SSE error:', err)
          resolve()
        },
      )
    })
  }

  async function resolveRouteChoice(intent, cancelled = false) {
    const pending = pendingRouteConfirm.value
    if (!pending || isStreaming.value) return
    const sessionId = currentSessionId.value
    if (!sessionId) return

    pendingRouteConfirm.value = null
    // 人工选择不新增用户消息：原始问题在第一轮已落库
    const assistantMsg = reactive({ role: 'assistant', content: '', streaming: true })
    messages.value.push(assistantMsg)
    isStreaming.value = true

    const payload = {
      session_id: String(sessionId),
      message: pending.message,
      forced_intent: intent,
      pending_token: pending.token,
      route_cancelled: cancelled,
    }

    await new Promise((resolve) => {
      streamChat(
        payload,
        (chunk) => applyChunk(chunk, assistantMsg, resolve),
        (err) => {
          assistantMsg.content += '\n\n[连接中断]'
          assistantMsg.streaming = false
          isStreaming.value = false
          console.error('SSE error:', err)
          resolve()
        },
      )
    })
  }

  function clearResult() {
    if (structuredResult.value) {
      sessionStorage.setItem(storageKey('dismissed-result'), resultKey(structuredResult.value))
    }
    structuredResult.value = null
  }

  function reset() {
    sessions.value = []
    currentSessionId.value = null
    messages.value = []
    isStreaming.value = false
    structuredResult.value = null
    pendingRouteConfirm.value = null
  }

  return {
    sessions, currentSessionId, messages, storageKey, saveSelection, clearSelection,
    isStreaming, structuredResult, pendingRouteConfirm,
    createSession, loadMessages, loadSessions, deleteSession, resetConversation, reset,
    sendMessage, resolveRouteChoice, clearResult,
  }
})
