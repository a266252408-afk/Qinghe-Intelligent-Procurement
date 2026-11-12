import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getToken, parseToken, removeToken, setToken } from './session'

// 模拟标签页存储，验证认证信息读写与异常 Token 的处理。
beforeEach(() => {
  const values = new Map()
  vi.stubGlobal('sessionStorage', {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  })
})

describe('标签页认证会话', () => {
  it('保存并清理当前标签页的 Token', () => {
    expect(getToken()).toBe('')
    setToken('example-token')
    expect(getToken()).toBe('example-token')
    removeToken()
    expect(getToken()).toBe('')
  })

  it('解码包含中文的 base64url claims', () => {
    const claims = { user_id: 1, username: '青禾采购员', team_id: 2 }
    const payload = Buffer.from(JSON.stringify(claims)).toString('base64url')
    setToken(`header.${payload}.signature`)
    expect(parseToken()).toEqual(claims)
  })

  it.each(['', 'invalid', 'a.!.c', 'a.bm90LWpzb24.c'])(
    '损坏的 Token 返回空值：%s',
    (token) => expect(parseToken(token)).toBeNull(),
  )
})
