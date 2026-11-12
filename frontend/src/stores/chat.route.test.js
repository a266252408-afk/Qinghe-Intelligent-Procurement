import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api/chat', () => ({ streamChat: vi.fn() }))
vi.mock('@/api/knowledge', () => ({
  knowledgeApi: {
    getMessages: vi.fn(),
    createSession: vi.fn(),
    listSessions: vi.fn(),
    deleteSession: vi.fn(),
  },
}))

import { streamChat } from '@/api/chat'
import { knowledgeApi } from '@/api/knowledge'
import { useChatStore } from '@/stores/chat'

const pendingPayload = {
  token: 'tok-1',
  status: 'pending',
  message: '香樟怎么处理',
  confidence: 0.42,
  threshold: 0.6,
  jev_intent: 'chat',
  options: [
    { intent: 'chat', label: '普通对话', probability: 0.42, executable: true, note: null },
    { intent: 'parse_list', label: '解析清单', probability: 0.24, executable: false, note: '需要先上传采购清单文件' },
  ],
  created_at: new Date().toISOString(),
  ttl_minutes: 30,
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  const values = new Map()
  vi.stubGlobal('sessionStorage', {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  })
})

describe('chat store route confirmation', () => {
  it('route_confirm 帧进入待确认状态，不写结构化结果', async () => {
    streamChat.mockImplementation((payload, onChunk) => {
      onChunk({ delta: '请确认', done: false, session_id: 1, type: 'route_confirm', data: pendingPayload })
      onChunk({ delta: '', done: true, session_id: 1 })
    })
    const store = useChatStore()
    store.currentSessionId = 1

    await store.sendMessage('香樟怎么处理')

    expect(store.pendingRouteConfirm).toEqual(pendingPayload)
    expect(store.structuredResult).toBeNull()
    expect(store.messages).toHaveLength(2)
  })

  it('人工选择只追加 assistant 消息并回传 forced_intent/pending_token', async () => {
    streamChat.mockImplementation((payload, onChunk) => {
      onChunk({ delta: '好的', done: true, session_id: 1 })
    })
    const store = useChatStore()
    store.currentSessionId = 1
    store.pendingRouteConfirm = pendingPayload

    await store.resolveRouteChoice('parse_list')

    expect(streamChat).toHaveBeenCalledWith(
      expect.objectContaining({
        forced_intent: 'parse_list',
        pending_token: 'tok-1',
        message: '香樟怎么处理',
        route_cancelled: false,
      }),
      expect.any(Function),
      expect.any(Function),
    )
    expect(store.messages).toHaveLength(1)
    expect(store.messages[0].role).toBe('assistant')
    expect(store.pendingRouteConfirm).toBeNull()
  })

  it('取消弹窗按 chat 继续并标记 route_cancelled', async () => {
    streamChat.mockImplementation((payload, onChunk) => {
      onChunk({ delta: '按对话回答', done: true, session_id: 1 })
    })
    const store = useChatStore()
    store.currentSessionId = 1
    store.pendingRouteConfirm = pendingPayload

    await store.resolveRouteChoice('chat', true)

    expect(streamChat).toHaveBeenCalledWith(
      expect.objectContaining({ forced_intent: 'chat', route_cancelled: true }),
      expect.any(Function),
      expect.any(Function),
    )
  })

  it('加载历史时恢复待确认弹窗，并排除结果抽屉', async () => {
    knowledgeApi.getMessages.mockResolvedValue([
      { role: 'user', content: '香樟怎么处理', metadata: null },
      {
        role: 'assistant',
        content: '请确认',
        metadata: { structured_type: 'route_confirm', structured_data: pendingPayload },
      },
    ])
    const store = useChatStore()

    await store.loadMessages(1)

    expect(store.pendingRouteConfirm).toEqual(pendingPayload)
    expect(store.structuredResult).toBeNull()
  })

  it('过期的待确认记录不再弹窗', async () => {
    const expired = {
      ...pendingPayload,
      created_at: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
    }
    knowledgeApi.getMessages.mockResolvedValue([
      {
        role: 'assistant',
        content: '请确认',
        metadata: { structured_type: 'route_confirm', structured_data: expired },
      },
    ])
    const store = useChatStore()

    await store.loadMessages(1)

    expect(store.pendingRouteConfirm).toBeNull()
  })

  it('重置会话清空待确认状态', () => {
    const store = useChatStore()
    store.pendingRouteConfirm = pendingPayload
    store.reset()
    expect(store.pendingRouteConfirm).toBeNull()
  })

  it('knowledge 帧写入结构化来源，答案进入 assistant 消息', async () => {
    const frame = {
      sources: ['industry'],
      results: [{ source: 'industry', source_file: '养护手册.pdf', content: '香樟养护要点', score: 0.9 }],
    }
    streamChat.mockImplementation((payload, onChunk) => {
      onChunk({ delta: '香樟养护应保持土壤湿润。', done: false, session_id: 1, type: 'knowledge', data: frame })
      onChunk({ delta: '', done: true, session_id: 1 })
    })
    const store = useChatStore()
    store.currentSessionId = 1

    await store.sendMessage('香樟树苗怎么养护')

    expect(store.structuredResult).toEqual({ type: 'knowledge', data: frame })
    expect(store.messages[1].content).toContain('土壤湿润')
  })
})
